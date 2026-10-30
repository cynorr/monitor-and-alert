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
from .preferences import INITIAL_PREFERENCES, validate_preferences
from .scan import candidates, previous_candidates, read_snapshot, build_day, publish_day, daily_chart, connect_daily, latest_completed_date, workspace_scope, enrich_snapshot, day_start
from .monitor import MonitorService
from .workspace import derive_day_view, normalize_ticker
from .storage import atomic_json
from .additional_info import AdditionalInfo
from .alerts import AlertEngine, price_cents
from .alerts.engine import symbol_key
from .alerts.sound import AlertSound
from .list_rules import apply_rules, focus_classification
from .features.events import days_to_earnings

log = logging.getLogger(__name__)


class Workbench:
    def __init__(self, workspace, runtime, daily_path, broker_factory, *, calendar=None, mock=False, only=None,
                 holdings_factory=None, pipeline=None, bars_path=None, sound=None, additional_info=None, trade_factory=None):
        self.workspace, self.runtime, self.daily_path = workspace, runtime, daily_path
        self.broker_factory, self.calendar = broker_factory, calendar or TradingCalendar()
        self.mock, self.only = mock, only
        self.bars_path = bars_path or RuntimePaths(runtime).bars_db
        self.pipeline = pipeline if not mock and only is None else None
        self.pipeline_task = None
        self.mode, self.monitor, self.monitor_task = 'scan', None, None
        self.holdings_factory = holdings_factory if not mock and only is None else None
        self.holdings, self.holdings_task = None, None
        self.trade = trade_factory() if trade_factory and not mock and only is None else None
        self.trade_task = None
        self.account_mode = "monitor"
        self.focus = ('', '5m')
        self.run_id = uuid.uuid4().hex
        self.started_at = int(time.time())
        self.selected_date = self.latest_date = workspace.date
        self.snapshot_cache, self.chart_cache, self.previous_cache = {}, {}, {}
        self.switching = self.generating = False
        self.preferences_path = runtime / 'preferences.json'
        self.additional = additional_info or AdditionalInfo(RuntimePaths(runtime).additional_info_dir, enabled=False)
        self.additional_task = None
        self.earnings_day = datetime.fromtimestamp(self.additional.now(), ET).date()
        self.additional.on_earnings_change = self.earnings_changed
        self.preferences = validate_preferences(json.loads(self.preferences_path.read_text()) if self.preferences_path.exists() else deepcopy(INITIAL_PREFERENCES))
        self.list_context = self._list_context()
        self.sound = sound if sound is not None else AlertSound() if not mock and only is None else None
        self.alerts = AlertEngine(RuntimePaths(runtime).alerts_db, self.calendar, sound=self.sound) if only is None else None
        workspace.on_change = self.workspace_changed
        self.workspace_changed()

    def refresh_list_quotes(self):
        if self.monitor:
            symbols = [row['symbol'] for row in self.scan_board(self.workspace.date)] if (
                not self.mock and self.only is None) else []
            self.monitor.update_quote_symbols(symbols)

    def refresh_alert_scope(self):
        now = int(self.monitor.now()) if self.monitor else int(time.time())
        day = datetime.fromtimestamp(now, ET).date().isoformat()
        snap_symbols = set(self.holdings.symbols_for(day)) if self.holdings else set()
        trade_symbols = set(self.trade.symbols(now)) if self.trade else set()
        symbols = snap_symbols | trade_symbols
        focus = {t.symbol for t in self.workspace.tickers()}
        if self.trade:
            self.trade.subscribe(focus | trade_symbols)
        if self.monitor:
            self.monitor.update_holdings(sorted(symbols))
            if self.monitor.intraday:
                if self.account_mode == 'trade' and self.trade:
                    open_symbols = self.trade.held_symbols()
                    displayed = trade_symbols
                else:
                    open_symbols = {symbol_key(h['ticker']) for h in self.holdings.base['holdings']
                                    if any(not s['closed_today'] for s in h['sequences'])} if self.holdings and self.holdings.base else set()
                    displayed = snap_symbols
                # Sold Today / Entries provide charts, never a holding-risk role.
                self.monitor.intraday.scope(focus - displayed, open_symbols)
        if self.alerts:
            known = (self.holdings_factory is None or (self.holdings is not None and self.holdings.base is not None))
            if self.trade:
                known = known and self.trade.runtime.state.account_updated_at is not None
            self.alerts.maintain(focus | symbols, known)

    def trade_state(self):
        if not self.trade:
            return None
        now = int(self.monitor.now()) if self.monitor else int(time.time())
        quotes = {symbol: self.monitor.quote(symbol, now) for symbol in self.trade.symbols(now)} if self.monitor else {}
        return self.trade.state(now, quotes)

    def alert_state(self):
        return self.alerts.state() if self.alerts else {'revision': 0, 'alerts': [], 'unread': [], 'eligible_symbols': [],
                'scope_known': True, 'sound': {'enabled': False, 'error': None, 'playing': []}, 'error': None}

    def focus_classifications(self, tickers):
        rows = {row['symbol'].removesuffix('.US'): row for row in self.list_snapshot(self.workspace.date)['rows']} if self.has_snapshot(self.workspace.date) else {}
        return {ticker: focus_classification(rows.get(ticker, {}), self.preferences) for ticker in tickers}

    def _list_context(self):
        states = self.workspace.data['statuses']
        return (self.workspace.date, frozenset(ticker for ticker, state in states.items() if state.get('status') == 'focus'))

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
        if self.workspace.date == value:
            self.workspace.reclassify(self.list_snapshot(value), self.preferences)

    def earnings_changed(self):
        self.earnings_day = datetime.fromtimestamp(self.additional.now(), ET).date()
        self.workspace_changed()

    def workspace_changed(self):
        if self.only is None and self.has_snapshot(self.workspace.date) and self.workspace.reclassify(self.list_snapshot(self.workspace.date), self.preferences):
            return  # The save callback publishes the completed classification.
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
        self.refresh_list_quotes()

    async def switch_mode(self, mode):
        if mode not in ('scan', 'monitor', 'trade'):
            raise ValueError('Choose Scan, Monitor or Trade')
        if mode == 'trade' and self.trade is None:
            raise ValueError('Trade is unavailable in this session')
        if self.switching:
            raise ValueError('Mode switch in progress')
        if mode == self.mode:
            return self.list_state()
        self.switching = True
        try:
            if mode in ('monitor', 'trade'):
                self.start_monitor()
            elif self.mock:
                # Mock Scan stays offline; only an explicit Monitor switch may connect.
                await self.stop_monitor()
            self.mode = mode
            if mode != 'scan':
                self.account_mode = mode
            self.refresh_alert_scope()
            self.refresh_list_quotes()
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
        self.monitor = MonitorService(tickers, self.runtime, broker, self.calendar, bars_path=self.bars_path,
                                   alerts=self.alerts, intraday=self.only is None)
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
        if not self.mock or self.mode in ('monitor', 'trade'):
            self.start_monitor()
        if self.pipeline and self.pipeline_task is None:
            self.pipeline_task = asyncio.create_task(self.pipeline.run(on_publish=self.scan_published))
        if self.trade and self.trade_task is None:
            self.trade_task = asyncio.create_task(self.trade.run(self.holdings_changed))
            self.refresh_alert_scope()
        if self.additional_task is None:
            self.additional_task = asyncio.create_task(self.additional.run())

    def scan_published(self, *_):
        # reload follows a new day only when the user was already following latest.
        self.workspace.reload()
        self.snapshot_cache.clear()
        self.chart_cache.clear()
        self.previous_cache.clear()
        if self.has_snapshot(self.workspace.date):
            self.workspace.reclassify(self.list_snapshot(self.workspace.date), self.preferences)
        self.refresh_list_quotes()
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
            await self.monitor.broker.aclose()
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
        if self.trade_task:
            self.trade_task.cancel()
            await asyncio.gather(self.trade_task, return_exceptions=True)
            self.trade_task = None
        if self.trade:
            await self.trade.runtime.close()
        if self.additional_task:
            self.additional_task.cancel()
            await asyncio.gather(self.additional_task, return_exceptions=True)
            self.additional_task = None
        if self.pipeline_task:
            self.pipeline_task.cancel()
            await asyncio.gather(self.pipeline_task, return_exceptions=True)
            self.pipeline_task = None
        if self.pipeline:
            await self.pipeline.close()
        await self.stop_monitor()
        if self.sound:
            await self.sound.close()
        if self.alerts:
            self.alerts.close()

    async def run(self):
        while True:
            if datetime.fromtimestamp(self.additional.now(), ET).date() != self.earnings_day:
                self.earnings_changed()
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

    def list_snapshot(self, value):
        snapshot = self.snapshot(value)
        if value != self.workspace.date:
            return snapshot
        today = datetime.fromtimestamp(self.additional.now(), ET).date()
        rows = {row['symbol']: row for row in snapshot['rows']}
        symbols = {symbol for symbol, row in rows.items() if row.get('candidate')}
        symbols.update(ticker + '.US' for ticker in self.workspace.data['statuses'])
        for symbol in sorted(symbols):
            event = self.additional.next_earnings(symbol, today.isoformat())
            rows[symbol] = {**rows.get(symbol, {'symbol': symbol, 'candidate': False}),
                            'days_to_earnings': days_to_earnings(event['date'] if event else None, today)}
        return {**snapshot, 'rows': list(rows.values())}

    def scan_board(self, value=None):
        value = value or self.selected_date
        if not self.has_snapshot(value):
            return []
        snapshot = self.list_snapshot(value)
        data = self.workspace.data if value == self.workspace.date else apply_rules(
            json.loads((self.workspace.root / value / 'workspace.json').read_text()), snapshot, self.preferences)
        prior = previous_candidates(self.workspace.root, value) if value != self.selected_date else self.previous()
        view = derive_day_view(value, candidates(snapshot), prior, data)
        rows = {row['symbol']: row for row in snapshot['rows']}
        priority = {ticker: index for index,ticker in enumerate(data.get('discover_order', []))}
        pins = {ticker: index for index, ticker in enumerate(data.get('pinned', []))}
        result = []
        for group, members in view.as_dict()['lists'].items():
            for index, ticker in enumerate(members):
                symbol = ticker + '.US'
                state = view.statuses.get(ticker, {})
                result.append({**rows.get(symbol, {}), **state, 'symbol': symbol, 'ticker': ticker,
                               'status': group, 'order_index': index, 'discover_priority': priority.get(ticker),
                               'pinned': ticker in pins, 'pin_index': pins.get(ticker),
                               'is_new': ticker in view.new})
        return result

    def monitor_board(self):
        local = {row['symbol']: row for row in self.scan_board(self.workspace.date)}
        result = []
        for row in self.monitor.board() if self.monitor else []:
            state = self.workspace.data['statuses'].get(row['ticker'], {})
            result.append({**local.get(row['symbol'], {}), **state, **row,
                           'section': state.get('section', 'unclassified'), 'tags': state.get('tags', []),
                           'manual_tags': state.get('manual_tags', []) if state.get('manual_tags_date') == self.workspace.date else []})
        return result

    def previous(self):
        if self.selected_date not in self.previous_cache:
            self.previous_cache[self.selected_date] = previous_candidates(self.workspace.root, self.selected_date)
        return self.previous_cache[self.selected_date]

    @property
    def symbols(self):
        if self.mode in ('monitor', 'trade'):
            return self.monitor.symbols if self.monitor else []
        return [row['symbol'] for row in self.scan_board()]

    @property
    def scan_mock(self):
        return self.mock or (self.has_snapshot() and self.snapshot()['mock'])

    def list_state(self):
        massive = self.pipeline.state() if self.pipeline else None
        now = int(self.monitor.now()) if self.monitor else int(time.time())
        holding_symbols = self.trade.symbols(now) if self.mode == 'trade' and self.trade else (
            self.holdings.symbols_for(datetime.fromtimestamp(now, ET).date().isoformat()) if self.holdings else [])
        return {'board': self.monitor_board() if self.mode in ('monitor', 'trade') else self.scan_board(),
                'mode': self.monitor.mode if self.mode in ('monitor', 'trade') and self.monitor else self.mode, 'app_mode': self.mode,
                'editable': self.only is None and (self.mode in ('monitor', 'trade') or (self.has_snapshot() and self.selected_date == self.workspace.date)),
                'workspace_error': self.workspace.error, 'date': self.workspace.date if self.mode in ('monitor', 'trade') else self.selected_date,
                'dates': sorted((p.parent.name for p in self.workspace.root.glob('*/scan.json')), reverse=True),
                'preferences': self.preferences, 'mock': self.scan_mock if self.mode == 'scan' else False,
                'holdings': self.holdings_state(), 'massive': massive,
                'trade': self.trade_state() if self.mode == 'trade' else None,
                'trade_enabled': self.trade is not None,
                'intraday': self.intraday_state(),
                'holding_symbols': holding_symbols, 'current_regular_session': self.calendar.is_open(now),
                'scan_running': self.generating or bool(massive and massive['running'])}

    def intraday_state(self):
        if self.monitor and self.monitor.intraday and (self.mode in ('monitor', 'trade') or self.selected_date == self.workspace.date):
            return self.monitor.intraday.state()
        return {'enabled': False, 'symbols': {}}

    def select(self, symbol, timeframe, source='watchlist'):
        if self.mode in ('monitor', 'trade'):
            if symbol not in self.symbols:
                raise ValueError('Ticker is outside this Monitor workspace')
            self.monitor.select(symbol, timeframe)
        elif symbol not in self.symbols:
            raise ValueError('Ticker is outside this Scan workspace')
        self.focus = symbol, timeframe

    def view(self, symbol, tf, revisions=None, source='watchlist'):
        if self.mode in ('monitor', 'trade'):
            return {**self.monitor.view(symbol, tf, revisions), 'app_mode': self.mode}
        value = self.selected_date
        key = value, symbol
        if key not in self.chart_cache:
            self.chart_cache[key] = daily_chart(self.daily_path, symbol, value, self.calendar)
        chart, summary = self.chart_cache[key]
        if revisions and revisions.get('1d') == chart['revision']:
            chart = {key:value for key,value in chart.items() if key not in ('bars','indicators')}
        return {'symbol': symbol, 'timeframe': tf, 'app_mode': self.mode, 'mode': self.mode, 'mock': self.scan_mock,
                'date': value, 'run_id': self.run_id, 'server_time': int(time.time()),
                'charts': {'1d': chart}, 'summary': summary, 'status': {'stage': 'full','errors': []},
                'quote': self.scan_quote(symbol)}

    def scan_quote(self, symbol):
        if (self.selected_date != self.workspace.date or self.mock or not self.monitor or
                symbol not in self.monitor.quotes.all_symbols):
            return {'regular': None, 'extended': {}, 'latest': None,
                    'connection_health': 'OFFLINE', 'error': None}
        return self.monitor.quotes.output(symbol, int(self.monitor.now()))

    def additional_info(self, symbol):
        return self.additional.info(symbol)

    async def list_action(self, payload):
        if not self.list_state()['editable']:
            raise ValueError('List editing unavailable for this session')
        action = payload['action']
        if action in ('pin', 'pin_move'):
            ticker = normalize_ticker(payload['ticker'])
            if action == 'pin':
                self.workspace.pin_ticker(ticker, payload['pinned'])
            else:
                self.workspace.move_pin(ticker, payload['index'])
            return self.list_state()
        if action in ('lookup','add'):
            ticker = normalize_ticker(payload['ticker'])
            if self.mode in ('monitor', 'trade'):
                info = await self.monitor.broker.validate_ticker(ticker)
            else:
                with closing(connect_daily(self.daily_path)) as db:
                    exists = db.execute("SELECT 1 FROM bars WHERE symbol=? AND timeframe='1d' AND ts<=? LIMIT 1",
                                        (ticker + '.US', day_start(self.calendar, self.selected_date))).fetchone()
                if not exists:
                    raise ValueError('US ticker not found')
                info = {'name': ''}
            if action == 'lookup':
                return {'ticker': ticker, 'name': info['name']}
            target = payload.get('list_name', 'discover' if self.mode == 'scan' else 'focus')
            if target not in (('discover', 'focus') if self.mode == 'scan' else ('focus',)):
                raise ValueError('Add new tickers to Focus')
            section = payload.get('section', 'unclassified')
            section = 'unclassified' if section in ('focus', 'wait') else section
            sections = {'unclassified'} | {tag['id'] for tag in self.preferences['tags'] if tag['role'] == 'setup'}
            if section not in sections:
                raise ValueError('Unknown setup section')
            existing = self.workspace.section(ticker)
            self.workspace.add_ticker(ticker, target, classification=self.focus_classifications([ticker])[ticker])
            if target == 'focus' and section != 'unclassified' and existing not in ('discover', 'excluded'):
                self.workspace.move_ticker(ticker, section, 0)
        elif action == 'hide':
            self.workspace.hide_ticker(normalize_ticker(payload['ticker']))
        elif action == 'keep':
            self.workspace.keep_ticker(normalize_ticker(payload['ticker']))
        elif action == 'tag':
            if not set(payload['tags']) <= {tag['id'] for tag in self.preferences['tags'] if tag['role'] in ('setup', 'label')}:
                raise ValueError('Manual Tags must be Setup or Label')
            self.workspace.set_manual_tags(normalize_ticker(payload['ticker']), payload['tags'])
        elif action == 'move' and 'target' in payload:
            ticker = normalize_ticker(payload['ticker'])
            classification = self.focus_classifications([ticker])[ticker] if payload['target'] == 'focus' else None
            self.workspace.move_member(ticker, payload['target'], candidates(self.snapshot(self.workspace.date)),
                                       classification=classification)
        elif action == 'move':
            sections = {'unclassified', 'focus', 'wait'} | {tag['id'] for tag in self.preferences['tags'] if tag['role'] == 'setup'}
            if payload['section'] not in sections:
                raise ValueError('Unknown setup section')
            self.workspace.move_ticker(normalize_ticker(payload['ticker']), payload['section'], payload['index'],
                                      list_name=payload.get('list_name', 'focus'))
        else:
            raise ValueError('Unknown list action')
        await self.prepare_lists()
        return self.list_state()

    async def action(self, resource, payload):
        if resource == 'additional-info':
            if payload.get('action') != 'refresh':
                raise ValueError('Expected additional info refresh')
            return self.additional.request_refresh()
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
            elif action == 'read':
                self.alerts.read(payload['symbol'])
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
                    # Ready data stays cached; explicit Refresh still resets the daily manual layer.
                    self.workspace.reload()
                    if value == self.workspace.date and (not self.pipeline or self.pipeline.state()['ready']):
                        self.workspace.reclassify(self.list_snapshot(value), self.preferences, reset=True)
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
        if path == '/v1/intraday-state':
            return self.intraday_state()
        if path == '/v1/additional-info':
            return self.additional_info(query['symbol'][0]) if 'symbol' in query else self.additional.state()
        if path == '/v1/alerts':
            return self.alert_state()
        if path == '/v1/trade':
            return self.trade_state()
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
                    'additional_info': self.additional.state(),
                    'holdings_task_active': bool(self.holdings_task and not self.holdings_task.done())}
        if path == '/v1/scan':
            return self.list_state()
        if path == '/v1/filter-catalog':
            from .preferences import CATALOG
            return CATALOG
        if self.mode in ('monitor', 'trade'):
            return await self.monitor.api(path, query)
        if path == '/v1/chart':
            symbol = query['symbol'][0]
            if symbol not in self.symbols:
                raise ValueError('Ticker is outside this Scan workspace')
            return self.view(symbol, '5m')
        raise ValueError('This endpoint is only available in Monitor mode')
