"""One workspace and background data tasks, with a global Scan/Monitor view."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from contextlib import closing
from copy import deepcopy

from .calendar import TradingCalendar, ET
from .paths import RuntimePaths
from .preferences import DEFAULT, validate_preferences
from .scan import candidates, previous_candidates, read_snapshot, build_day, publish_day, daily_chart, connect_daily, latest_completed_date, workspace_scope, enrich_snapshot
from .service import DataService
from .workspace import derive_day_view, normalize_ticker
from .store import atomic_json
from .symbol_directory import read_directory
from .alerts import AlertEngine, price_cents
from .alerts.engine import symbol_key
from .list_rules import focus_classification

log = logging.getLogger(__name__)


class Workbench:
    def __init__(self, workspace, runtime, daily_path, broker_factory, *, calendar=None, mock=False, only=None,
                 holdings_factory=None, pipeline=None, bars_path=None, notifier=None):
        self.workspace, self.runtime, self.daily_path = workspace, runtime, daily_path
        self.broker_factory, self.calendar = broker_factory, calendar or TradingCalendar()
        self.mock, self.only = mock, only
        self.bars_path = bars_path or RuntimePaths(runtime).bars_db
        self.pipeline = pipeline if not mock and only is None else None
        self.pipeline_task = None
        self.mode, self.monitor, self.monitor_task = 'scan', None, None
        self.holdings_factory = holdings_factory if not mock and only is None else None
        self.holdings, self.holdings_task = None, None
        self.focus = ('', '5m')
        self.run_id = uuid.uuid4().hex
        self.started_at = int(time.time())
        self.selected_date = self.latest_date = workspace.date
        self.snapshot_cache, self.chart_cache, self.previous_cache = {}, {}, {}
        self.switching = self.generating = False
        self.preferences_path = runtime / 'preferences.json'
        self.symbol_directory_path = RuntimePaths(runtime).symbol_directory
        self.symbol_directory_cache = None, {}
        self.preferences = validate_preferences(json.loads(self.preferences_path.read_text()) if self.preferences_path.exists() else deepcopy(DEFAULT))
        self.list_context = self._list_context()
        self.alerts = AlertEngine(RuntimePaths(runtime).alerts_db, self.calendar, notifier=notifier) if only is None else None
        self.refresh_alert_scope()
        workspace.on_change = self.workspace_changed

    def refresh_alert_scope(self):
        day = datetime.fromtimestamp(time.time(), ET).date().isoformat()
        symbols = self.holdings.symbols_for(day) if self.holdings else []
        if self.monitor:
            self.monitor.update_holdings(symbols)
        if self.alerts:
            allowed = {t.symbol for t in self.workspace.tickers()} | set(symbols)
            known = self.holdings_factory is None or (self.holdings is not None and self.holdings.base is not None)
            self.alerts.maintain(allowed, known)

    def alert_state(self):
        return self.alerts.state() if self.alerts else {'revision': 0, 'alerts': [], 'events': [], 'eligible_symbols': [],
                'scope_known': True, 'notification': {'available': False, 'authorization': 'unavailable', 'sound': False,
                                                     'error': 'Alerts are disabled for symbol-subset sessions'}, 'error': None}

    def focus_classifications(self, tickers):
        rows = {row['symbol'].removesuffix('.US'): row for row in self.snapshot(self.workspace.date)['rows']} if self.has_snapshot(self.workspace.date) else {}
        return {ticker: focus_classification(rows.get(ticker, {}), self.preferences) for ticker in tickers}

    def _list_context(self):
        states = self.workspace.data['statuses']
        return (self.workspace.date, frozenset(ticker for ticker, state in states.items() if state.get('status') == 'focus'),
                frozenset(ticker for ticker, state in states.items() if state.get('status') == 'excluded' and state.get('section') == 'review'))

    async def prepare_lists(self):
        """Refresh saved classifications from local Daily; never download on reads."""
        value = self.workspace.date
        if not self.has_snapshot(value):
            return
        tracked = workspace_scope(self.workspace.root, value)
        snapshot = self.snapshot(value)
        if self.daily_path.is_file():
            updated = await asyncio.to_thread(enrich_snapshot, self.daily_path, snapshot, self.calendar,
                                             tracked_tickers=tracked,
                                             log_path=self.runtime / 'invalid_ohlc.jsonl')
            if updated != snapshot:
                atomic_json(self.workspace.root / value / 'scan.json', updated)
                self.snapshot_cache.pop(value, None)
                self.chart_cache.clear()
                snapshot = updated
        if self.workspace.date == value:
            self.workspace.reclassify(snapshot, self.preferences)

    def workspace_changed(self):
        context = self._list_context()
        if context != self.list_context:
            self.list_context = context
            self.run_id = uuid.uuid4().hex
        if self.selected_date == self.latest_date:
            self.selected_date = self.workspace.date
        self.latest_date = self.workspace.date
        if self.monitor:
            tickers = self.workspace.tickers()
            if self.only:
                wanted = {symbol if symbol.endswith('.US') else symbol + '.US' for symbol in self.only}
                tickers = [ticker for ticker in tickers if ticker.symbol in wanted]
            self.monitor.update_tickers(tickers)
        self.refresh_alert_scope()

    async def switch_mode(self, mode):
        if mode not in ('scan', 'monitor'):
            raise ValueError('Choose Scan or Monitor')
        if self.switching:
            raise ValueError('Mode switch in progress')
        if mode == self.mode:
            return self.list_state()
        self.switching = True
        try:
            if mode == 'monitor':
                self.start_monitor()
            elif self.mock:
                # Mock Scan stays offline; only an explicit Monitor switch may connect.
                await self.stop_monitor()
            self.mode = mode
            self.run_id = uuid.uuid4().hex
            self.focus = (self.symbols[0] if self.symbols else '', self.focus[1])
            return self.list_state()
        finally:
            self.switching = False

    def start_monitor(self):
        if self.monitor is not None:
            return
        tickers = self.workspace.tickers()
        if self.only:
            wanted = {s if s.endswith('.US') else s + '.US' for s in self.only}
            tickers = [t for t in tickers if t.symbol in wanted]
        broker = self.broker_factory({ticker.symbol for ticker in tickers})
        self.monitor = DataService(tickers, self.runtime, broker, self.calendar, bars_path=self.bars_path, alerts=self.alerts)
        self.workspace_changed()
        self.monitor_task = asyncio.create_task(self.monitor.run())
        if self.holdings_factory:
            if self.holdings is None:
                self.holdings = self.holdings_factory()
            self.holdings_changed()
            self.holdings_task = asyncio.create_task(self.holdings.run(self.holdings_changed))

    async def start_background(self):
        if self.only is None:
            try:
                await self.prepare_lists()
            except (OSError, ValueError, sqlite3.Error):
                self.workspace.error = 'Could not refresh List from local Daily'
                log.warning('Local List preparation failed; keeping the saved workspace')
        if not self.mock or self.mode == 'monitor':
            self.start_monitor()
        if self.pipeline and self.pipeline_task is None:
            self.pipeline_task = asyncio.create_task(self.pipeline.run(on_publish=self.scan_published))

    def scan_published(self, *_):
        # reload follows a new day only when the user was already following latest.
        self.workspace.reload()
        self.snapshot_cache.clear()
        self.chart_cache.clear()
        self.previous_cache.clear()
        if self.has_snapshot(self.workspace.date):
            self.workspace.reclassify(self.snapshot(self.workspace.date), self.preferences)
        self.run_id = uuid.uuid4().hex

    async def stop_monitor(self):
        if self.holdings_task:
            self.holdings_task.cancel()
            await asyncio.gather(self.holdings_task, return_exceptions=True)
            self.holdings_task = None
        if self.monitor_task:
            self.monitor_task.cancel()
            await asyncio.gather(self.monitor_task, return_exceptions=True)
            self.monitor_task = None
        if self.monitor:
            self.monitor.broker.close()
            self.monitor.store.close()
            self.monitor = None

    def holdings_changed(self):
        self.refresh_alert_scope()

    def holdings_state(self):
        if self.mode != 'monitor' or self.holdings is None:
            return None
        quotes = {}
        now = int(self.monitor.now())
        for symbol in self.holdings.symbols:
            quote = self.monitor.quote(symbol, now)
            # Share the watchlist's official Daily-close correction for Chg%.
            quotes[symbol] = {'Intraday': quote['regular'], **quote['extended']} if quote['regular'] else quote['extended']
        return self.holdings.state(quotes, as_of=datetime.fromtimestamp(now, ET).date().isoformat())

    async def close(self):
        if self.pipeline_task:
            self.pipeline_task.cancel()
            await asyncio.gather(self.pipeline_task, return_exceptions=True)
            self.pipeline_task = None
        if self.pipeline:
            await self.pipeline.close()
        await self.stop_monitor()
        if self.alerts:
            self.alerts.close()

    async def run(self):
        while True:
            self.refresh_alert_scope()
            for name, task in (('Monitor', self.monitor_task), ('Holdings', self.holdings_task)):
                if task and task.done():
                    task.result()
                    raise RuntimeError(f'{name} task stopped unexpectedly')
            if self.pipeline_task and self.pipeline_task.done():
                self.pipeline_task.result()
            await asyncio.sleep(.2)

    def has_snapshot(self, value=None):
        return (self.workspace.root / (value or self.selected_date) / 'scan.json').is_file()

    def snapshot(self, value=None):
        value = value or self.selected_date
        path = self.workspace.root / value / 'scan.json'
        signature = path.stat().st_mtime_ns
        cached = self.snapshot_cache.get(value)
        if cached is None or cached[0] != signature:
            self.snapshot_cache[value] = signature, read_snapshot(self.workspace.root, value)
            self.chart_cache.clear()
            if cached:
                self.run_id = uuid.uuid4().hex
        return self.snapshot_cache[value][1]

    def scan_board(self, value=None):
        value = value or self.selected_date
        if not self.has_snapshot(value):
            return []
        snapshot = self.snapshot(value)
        data = self.workspace.data if value == self.workspace.date else json.loads((self.workspace.root / value / 'workspace.json').read_text())
        prior = previous_candidates(self.workspace.root, value) if value != self.selected_date else self.previous()
        view = derive_day_view(value, candidates(snapshot), prior, data)
        rows = {row['symbol']: row for row in snapshot['rows']}
        priority = {ticker: index for index,ticker in enumerate(data.get('discover_order', []))}
        result = []
        for group, members in view.as_dict()['lists'].items():
            for index, ticker in enumerate(members):
                symbol = ticker + '.US'
                state = view.statuses.get(ticker, {})
                result.append({**rows.get(symbol, {}), **state, 'symbol': symbol, 'ticker': ticker,
                               'status': group, 'order_index': index, 'discover_priority': priority.get(ticker),
                               'is_new': ticker in view.new, 'is_returned': ticker in view.returned})
        return result

    def monitor_board(self):
        local = {row['symbol']: row for row in self.scan_board(self.workspace.date)}
        result = []
        for row in self.monitor.board() if self.monitor else []:
            state = self.workspace.data['statuses'].get(row['ticker'], {})
            result.append({**local.get(row['symbol'], {}), **state, **row,
                           'section': state.get('section', 'unclassified'), 'tags': state.get('tags', []),
                           'manual_tags': state.get('manual_tags', []) if state.get('manual_tags_date') == self.workspace.date else []})
        if self.only is None:
            result.extend(row for row in local.values() if row['status'] == 'excluded' and row.get('section') == 'review')
        return result

    def is_review(self, symbol):
        state = self.workspace.data['statuses'].get(symbol.removesuffix('.US'), {})
        return state.get('status') == 'excluded' and state.get('section') == 'review'

    def previous(self):
        if self.selected_date not in self.previous_cache:
            self.previous_cache[self.selected_date] = previous_candidates(self.workspace.root, self.selected_date)
        return self.previous_cache[self.selected_date]

    @property
    def symbols(self):
        if self.mode == 'monitor':
            return list(dict.fromkeys((self.monitor.symbols if self.monitor else []) +
                                     [row['symbol'] for row in self.scan_board(self.workspace.date) if self.only is None and row['status'] == 'excluded' and row.get('section') == 'review']))
        return [row['symbol'] for row in self.scan_board()]

    @property
    def scan_mock(self):
        return self.mock or (self.has_snapshot() and self.snapshot()['mock'])

    def list_state(self):
        massive = self.pipeline.state() if self.pipeline else None
        return {'board': self.monitor_board() if self.mode == 'monitor' else self.scan_board(),
                'mode': self.monitor.mode if self.mode == 'monitor' and self.monitor else self.mode, 'app_mode': self.mode,
                'editable': self.only is None and (self.mode == 'monitor' or (self.has_snapshot() and self.selected_date == self.workspace.date)),
                'workspace_error': self.workspace.error, 'date': self.workspace.date if self.mode == 'monitor' else self.selected_date,
                'dates': sorted((p.parent.name for p in self.workspace.root.glob('*/scan.json')), reverse=True),
                'preferences': self.preferences, 'mock': self.scan_mock if self.mode == 'scan' else False,
                'holdings': self.holdings_state(), 'massive': massive,
                'scan_running': self.generating or bool(massive and massive['running'])}

    def select(self, symbol, timeframe, source='watchlist'):
        if self.mode == 'monitor':
            if symbol not in self.symbols:
                raise ValueError('Ticker is outside this Monitor workspace')
            if source == 'holdings' or not self.is_review(symbol):
                self.monitor.select(symbol, timeframe)
        elif symbol not in self.symbols:
            raise ValueError('Ticker is outside this Scan workspace')
        self.focus = symbol, timeframe

    def view(self, symbol, tf, revisions=None, source='watchlist'):
        review = self.mode == 'monitor' and source != 'holdings' and self.is_review(symbol)
        if self.mode == 'monitor' and not review:
            return {**self.monitor.view(symbol, tf, revisions), 'app_mode': 'monitor',
                    'security_name': self.security_name(symbol)}
        value = self.workspace.date if review else self.selected_date
        key = value, symbol
        if key not in self.chart_cache:
            self.chart_cache[key] = daily_chart(self.daily_path, symbol, value, self.calendar)
        chart, summary = self.chart_cache[key]
        if revisions and revisions.get('1d') == chart['revision']:
            chart = {key:value for key,value in chart.items() if key not in ('bars','indicators')}
        return {'symbol': symbol, 'timeframe': tf, 'app_mode': self.mode, 'mode': self.mode, 'mock': self.scan_mock,
                'security_name': self.security_name(symbol),
                'read_only_daily': review, 'date': value, 'run_id': self.run_id, 'server_time': int(time.time()),
                'charts': {'1d': chart}, 'summary': summary, 'status': {'stage': 'full','errors': []},
                'quote': {'regular': None, 'extended': {}, 'connection_health': 'OFFLINE', 'error': None}}

    def security_name(self, symbol):
        """Read optional local directory names, independent of chart data and brokers."""
        try:
            stat = self.symbol_directory_path.stat()
            signature = stat.st_mtime_ns, stat.st_size, stat.st_ino
        except OSError:
            self.symbol_directory_cache = None, {}
            return None
        cached_signature, symbols = self.symbol_directory_cache
        if cached_signature != signature:
            try:
                symbols = read_directory(self.symbol_directory_path)['symbols']
            except (OSError, ValueError):
                symbols = {}
            self.symbol_directory_cache = signature, symbols
        name = symbols.get(symbol, {}).get('name')
        return name.strip() or None if isinstance(name, str) else None

    async def list_action(self, payload):
        if not self.list_state()['editable']:
            raise ValueError('List editing unavailable for this session')
        action = payload['action']
        if action in ('lookup','add'):
            ticker = normalize_ticker(payload['ticker'])
            if self.mode == 'monitor':
                info = await self.monitor.broker.validate_ticker(ticker)
            else:
                with closing(connect_daily(self.daily_path)) as db:
                    exists = db.execute("SELECT 1 FROM bars WHERE symbol=? AND timeframe='1d' LIMIT 1", (ticker + '.US',)).fetchone()
                if not exists:
                    raise ValueError('US ticker not found')
                info = {'name': 'Daily database'}
            if action == 'lookup':
                return {'ticker': ticker, 'name': info['name']}
            if payload.get('list_name', 'focus') != 'focus':
                raise ValueError('Add new tickers to Focus')
            section = payload.get('section', 'unclassified')
            section = 'unclassified' if section in ('focus', 'wait') else section
            sections = {'unclassified'} | {tag['id'] for tag in self.preferences['tags'] if tag['role'] == 'setup'}
            if section not in sections:
                raise ValueError('Unknown setup section')
            existing = self.workspace.section(ticker)
            self.workspace.add_ticker(ticker, 'focus', classification=self.focus_classifications([ticker])[ticker])
            if section != 'unclassified' and existing not in ('discover', 'excluded'):
                self.workspace.move_ticker(ticker, section, 0)
        elif action == 'delete':
            self.workspace.delete_ticker(normalize_ticker(payload['ticker']))
        elif action == 'keep':
            self.workspace.keep_ticker(normalize_ticker(payload['ticker']))
        elif action == 'tag':
            if not set(payload['tags']) <= {tag['id'] for tag in self.preferences['tags'] if tag['id'] != 'default'}:
                raise ValueError('Unknown Tag')
            self.workspace.set_manual_tags(normalize_ticker(payload['ticker']), payload['tags'])
        elif action == 'move' and not payload.get('tickers'):
            sections = {'unclassified', 'focus', 'wait'} | {tag['id'] for tag in self.preferences['tags'] if tag['role'] == 'setup'}
            if payload['section'] not in sections:
                raise ValueError('Unknown setup section')
            self.workspace.move_ticker(normalize_ticker(payload['ticker']), payload['section'], payload['index'],
                                      list_name=payload.get('list_name', 'focus'))
        elif action == 'move':
            snapshot = self.snapshot(self.workspace.date)
            self.workspace.move_members(payload['tickers'], payload['source'], payload['target'], candidates(snapshot),
                                        previous_candidates(self.workspace.root, snapshot['date']),
                                        classifications=self.focus_classifications(payload['tickers']))
        else:
            raise ValueError('Unknown list action')
        await self.prepare_lists()
        return self.list_state()

    async def action(self, resource, payload):
        if resource == 'alerts':
            if self.alerts is None:
                raise ValueError('Alerts are disabled for symbol-subset sessions')
            action = payload.get('action')
            self.refresh_alert_scope()
            if action == 'create':
                if payload.get('mode') != self.mode:
                    raise ValueError('Alert creation belongs to a previous mode')
                symbol = symbol_key(payload['symbol'])
                price_cents(payload['price'])
                ticker = symbol.removesuffix('.US')
                promoted = False
                if self.workspace.section(ticker) != 'focus' and (symbol not in self.alerts.allowed or payload.get('mode') == 'scan'):
                    # Historical Scan gestures still mutate the effective workspace.
                    if payload.get('mode') != 'scan' or symbol not in self.symbols:
                        raise ValueError('Choose a current Focus/Holdings symbol or a Scan chart')
                    self.workspace.add_ticker(ticker, classification=self.focus_classifications([ticker])[ticker])
                    promoted = True
                try:
                    self.alerts.create(symbol, payload['price'])
                except sqlite3.Error:
                    if promoted:
                        return {**self.alert_state(), 'error': 'Added to Focus; alert was not saved', 'partial': True}
                    raise
            elif action == 'rearm':
                self.alerts.rearm(payload['id'], payload['price'], payload['generation'])
            elif action == 'delete':
                self.alerts.delete(payload['id'])
            elif action == 'acknowledge':
                self.alerts.acknowledge(payload['event_id'])
            elif action == 'notifications':
                if self.alerts.notifier:
                    self.alerts.notifier.request_settings()
            else:
                raise ValueError('Unknown alert action')
            return self.alert_state()
        if resource == 'mode':
            return await self.switch_mode(payload['mode'])
        if resource == 'scan':
            if self.mode != 'scan':
                raise ValueError('Switch to Scan first')
            if 'date' in payload and not payload.get('generate'):
                if payload['date'] not in self.list_state()['dates']:
                    raise ValueError('Scan date not found')
                self.selected_date = payload['date']
                self.run_id = uuid.uuid4().hex
            elif payload.get('generate'):
                if 'date' in payload:
                    raise ValueError('Use the scan --date command to rebuild a specified date')
                if self.generating or (self.pipeline_task and not self.pipeline_task.done()):
                    raise ValueError('Scan generation in progress')
                self.generating = True
                try:
                    if self.pipeline:
                        self.pipeline_task = asyncio.create_task(self.pipeline.run(on_publish=self.scan_published))
                        await self.pipeline_task
                        value = self.pipeline.state()['features']['date']
                    else:
                        value = latest_completed_date(self.daily_path)
                        if not self.has_snapshot(value):
                            tracked = workspace_scope(self.workspace.root, value)
                            snapshot = await asyncio.to_thread(build_day, self.daily_path, value, self.calendar,
                                                                log_path=self.runtime / 'invalid_ohlc.jsonl', mock=self.mock,
                                                                tracked_tickers=tracked,
                                                                directory_path=RuntimePaths(self.runtime).symbol_directory)
                            publish_day(self.workspace.root, snapshot)
                            self.scan_published()
                    if value and value != self.selected_date:
                        self.selected_date = value
                        self.run_id = uuid.uuid4().hex
                finally:
                    self.generating = False
            return self.list_state()
        if resource == 'preferences':
            updated = validate_preferences(deepcopy(payload))
            self.preferences_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
            self.preferences = updated
            await self.prepare_lists()
            return self.list_state()
        raise ValueError('Unknown action')

    async def api(self, path, query):
        if path == '/v1/alerts':
            return self.alert_state()
        if path == '/v1/holdings':
            return self.holdings_state()
        if path == '/health':
            monitor = await self.monitor.api(path, query) if self.monitor else {}
            return {**monitor, 'service': 'running', 'mode': self.mode, 'broker_active': self.monitor is not None,
                    'quote_health': monitor.get('quote_health', 'OFFLINE'),
                    'mock': self.scan_mock if self.mode == 'scan' else False,
                    'alerts': {'enabled': self.alerts is not None, 'count': len(self.alerts.alerts) if self.alerts else 0,
                               'error': self.alerts.error if self.alerts else None},
                    'massive': self.pipeline.state() if self.pipeline else None,
                    'holdings_task_active': bool(self.holdings_task and not self.holdings_task.done())}
        if path == '/v1/scan':
            return self.list_state()
        if path == '/v1/filter-catalog':
            from .preferences import CATALOG
            return CATALOG
        if path == '/v1/chart' and self.mode == 'monitor' and self.is_review(query['symbol'][0]):
            return self.view(query['symbol'][0], query.get('timeframe', ['5m'])[0], source=query.get('source', ['watchlist'])[0])
        if self.mode == 'monitor':
            result = await self.monitor.api(path, query)
            if path == '/v1/chart':
                result = {**result, 'security_name': self.security_name(query['symbol'][0])}
            return result
        if path == '/v1/chart':
            symbol = query['symbol'][0]
            if symbol not in self.symbols:
                raise ValueError('Ticker is outside this Scan workspace')
            return self.view(symbol, '5m')
        raise ValueError('This endpoint is only available in Monitor mode')
