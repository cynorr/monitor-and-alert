"""Application lifecycle: one active Scan or Monitor mode, one Workspace."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import closing
from copy import deepcopy

from .calendar import TradingCalendar
from .preferences import DEFAULT, validate_preferences
from .scan import candidates, previous_candidates, read_snapshot, build_day, publish_day, daily_chart, connect_daily
from .service import DataService
from .workspace import derive_day_view, normalize_ticker


class Workbench:
    def __init__(self, workspace, runtime, daily_path, broker_factory, *, calendar=None, mock=False, only=None,
                 holdings_factory=None):
        self.workspace, self.runtime, self.daily_path = workspace, runtime, daily_path
        self.broker_factory, self.calendar = broker_factory, calendar or TradingCalendar()
        self.mock, self.only = mock, only
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
        self.preferences = json.loads(self.preferences_path.read_text()) if self.preferences_path.exists() else deepcopy(DEFAULT)
        workspace.on_change = self.workspace_changed

    def workspace_changed(self):
        if self.selected_date == self.latest_date:
            self.selected_date = self.workspace.date
        self.latest_date = self.workspace.date
        if self.monitor:
            tickers = self.workspace.tickers()
            if self.only:
                wanted = {symbol if symbol.endswith('.US') else symbol + '.US' for symbol in self.only}
                tickers = [ticker for ticker in tickers if ticker.symbol in wanted]
            self.monitor.update_tickers(tickers)

    async def switch_mode(self, mode):
        if mode not in ('scan', 'monitor'):
            raise ValueError('Choose Scan or Monitor')
        if self.switching or self.generating:
            raise ValueError('Mode switch or Scan generation in progress')
        if mode == self.mode:
            return self.list_state()
        self.switching = True
        try:
            if mode == 'monitor':
                tickers = self.workspace.tickers()
                broker = self.broker_factory({ticker.symbol for ticker in tickers})
                self.monitor = DataService(tickers, self.runtime, broker, self.calendar)
                self.workspace_changed()
                self.monitor_task = asyncio.create_task(self.monitor.run())
                if self.holdings_factory:
                    if self.holdings is None:
                        self.holdings = self.holdings_factory()
                    self.holdings_changed()
                    self.holdings_task = asyncio.create_task(self.holdings.run(self.holdings_changed))
            else:
                self.snapshot()  # Verify the local source before stopping the current mode.
                with closing(connect_daily(self.daily_path)) as db:
                    db.execute('SELECT symbol,timeframe,ts,open,high,low,close,volume,turnover FROM bars LIMIT 0')
                await self.stop_monitor()
            self.mode = mode
            self.run_id = uuid.uuid4().hex
            self.focus = (self.symbols[0] if self.symbols else '', self.focus[1])
            return self.list_state()
        finally:
            self.switching = False

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
        if self.monitor and self.holdings:
            self.monitor.update_holdings(self.holdings.symbols)

    def holdings_state(self):
        if self.mode != 'monitor' or self.holdings is None:
            return None
        return self.holdings.state(self.monitor.quotes.values)

    async def close(self):
        await self.stop_monitor()

    async def run(self):
        while True:
            if self.monitor_task and self.monitor_task.done():
                self.monitor_task.result()
            await asyncio.sleep(.2)

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

    def scan_board(self):
        snapshot = self.snapshot()
        data = self.workspace.data if self.selected_date == self.workspace.date else json.loads((self.workspace.root / self.selected_date / 'workspace.json').read_text())
        view = derive_day_view(self.selected_date, candidates(snapshot), self.previous(), data)
        rows = {row['symbol']: row for row in snapshot['rows']}
        priority = {ticker: index for index,ticker in enumerate(data.get('discover_order', []))}
        result = []
        for group, members in view.as_dict()['lists'].items():
            for index, ticker in enumerate(members):
                symbol = ticker + '.US'
                result.append({**rows.get(symbol, {}), 'symbol': symbol, 'ticker': ticker,
                               'status': group, 'order_index': index, 'discover_priority': priority.get(ticker),
                               'is_new': ticker in view.new, 'is_returned': ticker in view.returned})
        return result

    def previous(self):
        if self.selected_date not in self.previous_cache:
            self.previous_cache[self.selected_date] = previous_candidates(self.workspace.root, self.selected_date)
        return self.previous_cache[self.selected_date]

    @property
    def symbols(self):
        return self.monitor.symbols if self.mode == 'monitor' else [row['symbol'] for row in self.scan_board()]

    @property
    def scan_mock(self):
        return self.mock or self.snapshot()['mock']

    def list_state(self):
        return {'board': self.monitor.board() if self.mode == 'monitor' else self.scan_board(),
                'mode': self.monitor.mode if self.mode == 'monitor' else 'scan', 'app_mode': self.mode,
                'editable': self.only is None and (self.mode == 'monitor' or self.selected_date == self.workspace.date),
                'workspace_error': self.workspace.error, 'date': self.selected_date,
                'dates': sorted((p.parent.name for p in self.workspace.root.glob('*/scan.json')), reverse=True),
                'preferences': self.preferences, 'mock': self.scan_mock if self.mode == 'scan' else False,
                'holdings': self.holdings_state()}

    def select(self, symbol, timeframe):
        if self.mode == 'monitor':
            self.monitor.select(symbol, timeframe)
        elif symbol not in self.symbols:
            raise ValueError('Ticker is outside this Scan workspace')
        self.focus = symbol, timeframe

    def view(self, symbol, tf, revisions=None):
        if self.mode == 'monitor':
            return {**self.monitor.view(symbol, tf, revisions), 'app_mode': 'monitor'}
        key = self.selected_date, symbol
        if key not in self.chart_cache:
            self.chart_cache[key] = daily_chart(self.daily_path, symbol, self.selected_date, self.calendar)
        chart, summary = self.chart_cache[key]
        if revisions and revisions.get('1d') == chart['revision']:
            chart = {key:value for key,value in chart.items() if key not in ('bars','indicators')}
        return {'symbol': symbol, 'timeframe': tf, 'app_mode': 'scan', 'mode': 'scan', 'mock': self.scan_mock,
                'date': self.selected_date, 'run_id': self.run_id, 'server_time': int(time.time()),
                'charts': {'1d': chart}, 'summary': summary, 'status': {'stage': 'full','errors': []},
                'quote': {'regular': None, 'extended': {}, 'connection_health': 'OFFLINE', 'error': None}}

    async def list_action(self, payload):
        if not self.list_state()['editable']:
            raise ValueError('List editing unavailable for this session')
        if self.mode == 'monitor':
            # Existing mutations share the same Workspace and its single callback.
            self.monitor.workspace = self.workspace
            return {**await self.monitor.list_action(payload), **self.list_state()}
        action = payload['action']
        if action in ('lookup','add'):
            ticker = normalize_ticker(payload['ticker'])
            with closing(connect_daily(self.daily_path)) as db:
                exists = db.execute("SELECT 1 FROM bars WHERE symbol=? AND timeframe='1d' LIMIT 1", (ticker + '.US',)).fetchone()
            if not exists:
                raise ValueError('US ticker not found')
            if action == 'lookup':
                return {'ticker': ticker, 'name': 'Daily database'}
            self.workspace.add_ticker(ticker, payload['section'])
        elif action == 'delete':
            self.workspace.delete_ticker(normalize_ticker(payload['ticker']))
        elif action == 'move' and payload.get('section') in ('focus','wait') and not payload.get('tickers'):
            self.workspace.move_ticker(normalize_ticker(payload['ticker']), payload['section'], payload['index'])
        elif action == 'move':
            self.workspace.move_members(payload['tickers'], payload['source'], payload['target'], candidates(self.snapshot()),
                                        self.previous())
        else:
            raise ValueError('Unknown list action')
        return self.list_state()

    async def action(self, resource, payload):
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
                if self.generating:
                    raise ValueError('Scan generation in progress')
                self.generating = True
                try:
                    snapshot = await asyncio.to_thread(build_day, self.daily_path, payload['date'], self.calendar,
                                                        log_path=self.runtime / 'invalid_ohlc.jsonl', mock=self.scan_mock)
                    publish_day(self.workspace.root, snapshot)
                    self.workspace.reload()
                    self.snapshot_cache.pop(payload['date'], None)
                    self.chart_cache.clear()
                    self.previous_cache.clear()
                    self.run_id = uuid.uuid4().hex
                finally:
                    self.generating = False
            return self.list_state()
        if resource == 'preferences':
            updated = validate_preferences(deepcopy(payload))
            self.preferences_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
            self.preferences = updated
            return self.list_state()
        raise ValueError('Unknown action')

    async def api(self, path, query):
        if path == '/v1/holdings':
            return self.holdings_state()
        if path == '/health':
            monitor = await self.monitor.api(path, query) if self.monitor else {}
            return {**monitor, 'service': 'running', 'mode': self.mode, 'broker_active': self.monitor is not None,
                    'quote_health': monitor.get('quote_health', 'OFFLINE'),
                    'mock': self.scan_mock if self.mode == 'scan' else False}
        if path == '/v1/scan':
            return self.list_state()
        if path == '/v1/filter-catalog':
            from .preferences import CATALOG
            return CATALOG
        if self.mode == 'monitor':
            return await self.monitor.api(path, query)
        if path == '/v1/chart':
            symbol = query['symbol'][0]
            if symbol not in self.symbols:
                raise ValueError('Ticker is outside this Scan workspace')
            return self.view(symbol, '5m')
        raise ValueError('This endpoint is only available in Monitor mode')
