"""Monitor orchestration: scoped market data, history tasks and consumer views."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .calendar import ET, PHASES, INTRADAY, TradingCalendar
from .chart_cache import ChartCache
from .longbridge.history import BarDownloader, HistoryValidator, parse_candle, sdk_timestamp
from .longbridge.realtime import RealtimeFeed
from .storage import BarStore, bar_row, append_ohlc_log, ohlc_comparison
from .intraday_state import IntradayState


@dataclass
class SyncState:
    pending: bool = True
    refresh: bool = True
    complete: bool = False
    target: int | None = None
    due: float = 0
    attempt: int = 0
    limit: int = 4  # Initial attempt plus three retries; later 5m rounds get three attempts.
    error: str | None = None
    alert: bool = False
    task: asyncio.Task | None = None
    background: bool = False
    loading: bool = False


class MonitorService:
    def __init__(self, tickers, runtime: Path, broker=None, calendar=None, clock=None, *, bars_path=None, alerts=None, intraday=False):
        self.tickers = tickers
        self.holdings_symbols = []
        self.quote_symbols = []
        self.symbols = [t.symbol for t in tickers]
        self.runtime, self.broker = runtime, broker
        self.now = clock or time.time
        self.mode = 'live'
        self.calendar = calendar or TradingCalendar()
        self.store = BarStore(bars_path or runtime / 'bars.sqlite3', self.calendar, set(self.symbols))
        self.validator = HistoryValidator(self.store, self.calendar)
        self.charts = ChartCache(self.store, self.calendar, clock=self.now)
        self.alerts = alerts
        self.intraday = IntradayState(self.charts, notify=alerts.notify if alerts else None, clock=self.now) if intraday else None
        self.downloader = BarDownloader(broker, self.store, self.calendar, clock=self.now) if broker else None
        self.quotes = RealtimeFeed(broker, self.symbols, self.calendar, on_quote=self.apply_quote,
                                   on_reconnect=self.check_windows, on_reset=self.reset_realtime,
                                   on_candle=self.apply_candles, candle_priority=self.candle_priority) if broker else None
        self.run_id = uuid.uuid4().hex
        self.started_at = int(self.now())
        self.session = self.calendar.window_session(self.started_at)
        self.focus = (self.symbols[0] if self.symbols else '', '5m')
        self.sync = {(symbol, tf): self.cached_state(symbol, tf) for symbol in self.symbols for tf in PHASES}
        self.check_windows()
        self.workspace = None
        self.workspace_subset = None
        self.retired_tasks = set()

    def attach_workspace(self, workspace, only=None):
        self.workspace = workspace
        self.workspace_subset = {s if s.endswith('.US') else s + '.US' for s in only} if only else None

        def changed():
            tickers = workspace.tickers()
            if self.workspace_subset is not None:
                tickers = [t for t in tickers if t.symbol in self.workspace_subset]
            self.update_tickers(tickers)

        workspace.on_change = changed
        changed()

    def update_tickers(self, tickers):
        self.tickers = tickers
        self._update_symbols()

    def update_holdings(self, symbols):
        self.holdings_symbols = list(symbols)
        self._update_symbols()

    def update_quote_symbols(self, symbols):
        self.quote_symbols = list(dict.fromkeys(symbols))
        self._update_quote_scope()

    def _update_quote_scope(self):
        if self.broker:
            self.broker.allowed = frozenset(self.symbols) | set(self.quote_symbols)
            self.broker.candle_allowed = frozenset(self.symbols)
        if self.quotes:
            self.quotes.set_symbols(self.symbols, self.quote_symbols)

    def _update_symbols(self):
        symbols = list(dict.fromkeys([t.symbol for t in self.tickers] + self.holdings_symbols))
        removed = set(self.symbols) - set(symbols)
        added = set(symbols) - set(self.symbols)
        self.symbols = symbols
        self.store.allowed = frozenset(symbols)
        for key in list(self.sync):
            if key[0] in removed:
                state = self.sync.pop(key)
                if state.task is not None:
                    state.task.cancel()
                    self.retired_tasks.add(state.task)
                    state.task.add_done_callback(self.retired_tasks.discard)
        for symbol in added:
            for tf in PHASES:
                self.sync[symbol, tf] = self.cached_state(symbol, tf)
        for symbol in removed:
            self.charts.remove(symbol)
        if self.focus[0] not in symbols:
            self.focus = (symbols[0] if symbols else '', self.focus[1])
        self._update_quote_scope()
        self.check_windows()

    def list_state(self):
        return {'board': self.board(), 'mode': self.mode,
                'current_regular_session': self.calendar.is_open(int(self.now())),
                'editable': self.workspace is not None and self.workspace_subset is None,
                'workspace_error': self.workspace.error if self.workspace else None}

    async def list_action(self, payload):
        from .workspace import normalize_ticker
        if self.workspace is None or self.workspace_subset is not None:
            raise ValueError('List editing unavailable for this session')
        action, ticker = payload.get('action'), normalize_ticker(payload.get('ticker', ''))
        section = payload.get('section')
        if action in {'lookup', 'add'}:
            if action == 'add':
                if payload.get('list_name', 'focus') != 'focus':
                    raise ValueError('Add new tickers to Focus')
                if self.workspace.section(ticker) == 'focus':
                    self.workspace.keep_ticker(ticker)
                    return {**self.list_state(), 'notice': 'Ticker already in Focus'}
            if self.broker is None:
                raise ValueError('Ticker validation unavailable')
            info = await self.broker.validate_ticker(ticker)
            if action == 'lookup':
                return {'ticker': ticker, 'name': info['name']}
            self.workspace.add_ticker(ticker, 'focus')
            if section not in (None, 'focus', 'wait', 'unclassified'):
                self.workspace.move_ticker(ticker, section, 0)
            return {**self.list_state(), 'notice': f"Added {ticker} · {info['name']}"}
        if action == 'hide':
            self.workspace.hide_ticker(ticker)
        elif action == 'move':
            self.workspace.move_ticker(ticker, section, payload.get('index'), list_name=payload.get('list_name', 'focus'))
        elif action == 'keep':
            self.workspace.add_ticker(ticker, 'focus')
        elif action == 'tag':
            self.workspace.set_manual_tags(ticker, payload.get('tags', []))
        elif action == 'pin':
            self.workspace.pin_ticker(ticker, payload['pinned'])
        elif action == 'pin_move':
            self.workspace.move_pin(ticker, payload['index'])
        else:
            raise ValueError('Unknown list action')
        return self.list_state()

    def validate(self, symbol, now=None):
        return self.validator.validate(symbol, int(self.now()) if now is None else now)

    def select(self, symbol, timeframe, source='watchlist'):
        self.store.check(symbol)
        if timeframe not in INTRADAY:
            raise ValueError('Invalid intraday timeframe')
        self.focus = (symbol, timeframe)

    def reset_realtime(self):
        if self.alerts:
            self.alerts.reset()
        if self.intraday:
            self.intraday.recover()

    def recover(self):
        self.reset_realtime()
        if self.quotes:
            self.quotes.recover()
        self.check_windows()

    def cached_state(self, symbol, tf):
        batch = self.store.batch(symbol, tf)
        latest = self.store.latest(symbol, tf)
        if batch and batch.get('session', [None])[0] == self.session[0] and latest is not None:
            return SyncState(pending=False, refresh=False, complete=True, target=latest)
        return SyncState()

    def check_windows(self):
        self._schedule(int(self.now()))

    def refresh_windows(self):
        for state in self.sync.values():
            state.pending = state.refresh = True
            state.complete = False
            state.due = state.attempt = 0
            state.limit = 4

    def window_ready(self, symbol, tf, now=None):
        now = int(self.now()) if now is None else now
        if self.broker is None:
            return self.validator.check(symbol, tf, now)['complete']
        return self.session[0] == self.calendar.window_session(now)[0] and self.sync[symbol, tf].complete

    def apply_quote(self, symbol, quote):
        if self.alerts:
            self.alerts.quote(symbol, quote)
        if self.intraday:
            self.intraday.quote(symbol, quote)

    def apply_candles(self, symbol, tf, items, *, initial=False):
        self.store.check(symbol)
        now = int(self.now())
        day = datetime.fromtimestamp(now, ET).date()
        rows, anomalies = [], []
        for item in items:
            if datetime.fromtimestamp(sdk_timestamp(item.timestamp), ET).date() != day:
                continue
            bar = parse_candle(item, symbol, tf, self.calendar, now, closed=False)
            rows.append(bar_row(bar))
            if bar.invalid_range:
                anomalies.append(ohlc_comparison(bar, self.calendar, now, 'Intraday',
                    {key: str(getattr(item, key)) for key in ('open', 'high', 'low', 'close', 'volume')}))
        append_ohlc_log(self.store.path.parent / 'invalid_ohlc.jsonl', anomalies)
        if rows and self.charts.apply_candles(symbol, tf, rows, replace=initial) and self.intraday:
            self.intraday.update(symbol, now)
        return bool(rows)

    def candle_priority(self, key):
        symbol, tf = key
        order = ('5m', '15m', '1d', '30m', '1h', '2h')
        selected = symbol == self.focus[0] and tf in ('5m', '1d', self.focus[1])
        return (0 if selected else 1 if tf in ('5m', '15m') else 2,
                self.symbols.index(symbol), order.index(tf))

    def priority(self, key):
        symbol, tf = key
        state = self.sync[key]
        selected = symbol == self.focus[0]
        order = ('5m', '1d', *PHASES[2:])
        if not state.refresh:
            return (-2 if selected else -1, 0)
        if selected and tf in ('5m', '1d', self.focus[1]):
            return (0, order.index(tf))
        return (1 if tf in ('5m', '1d') else 2, self.symbols.index(symbol), order.index(tf))

    async def _execute(self, key):
        state = self.sync[key]
        count = 1000 if state.refresh else 2
        state.refresh = False
        state.loading = count == 1000
        try:
            batch = await self.downloader.fetch(*key, count=count, background=state.background)
            if batch is None:
                state.refresh = state.pending = True
                state.due = 0
                return
            check = self.validator.check(*key, int(self.now()))
            if not check['complete']:
                raise ValueError('; '.join(check['errors']))
        except Exception as exc:
            state.error = str(exc)
            state.refresh = state.pending = True
            state.attempt += 1
            if state.attempt >= state.limit:
                state.alert = True
                state.attempt, state.limit = 0, 3
                state.due = self.calendar.next_close('5m', int(self.now())) + 2
            else:
                state.due = self.now() + (2, 5, 10)[state.attempt - 1]
        else:
            state.complete = state.complete or not state.refresh
            state.pending = state.refresh
            state.target = check['target']
            state.error, state.alert = None, False
            state.attempt, state.limit, state.due = 0, 4, 0
            if self.intraday:
                self.intraday.update(key[0], int(self.now()))
        finally:
            state.loading = False

    def _schedule(self, now):
        session = self.calendar.window_session(now)
        if session[0] != self.session[0]:
            self.session = session
            self.charts.new_day()
            self.reset_realtime()
            if self.intraday:
                self.intraday.reset()
            self.refresh_windows()
        else:
            self.session = session
        targets = {tf: self.calendar.latest_closed(tf, now) for tf in PHASES}
        for (symbol, tf), state in self.sync.items():
            if state.pending or state.task is not None or state.target == targets[tf]:
                continue
            state.pending = True
            state.due = self.calendar.bar_end(targets[tf], tf) + 2
            # A missed boundary uses the same recent-1000 refresh, never pagination.
            state.refresh = state.target is None or len(self.calendar.expected(tf, state.target + 1, targets[tf], now)) > 1

    async def scheduler(self, initial_only=False):
        previous_time = self.now()
        try:
            while True:
                for state in self.sync.values():
                    if state.task is not None and state.task.done():
                        state.task.result()
                        state.task = None
                now = self.now()
                if now - previous_time > 30:
                    self.recover()
                previous_time = now
                if not initial_only:
                    self._schedule(int(now))
                if self.intraday:
                    self.intraday.tick(now)
                running = sum(s.task is not None for s in self.sync.values())
                background = sum(s.task is not None and s.background for s in self.sync.values())
                for key in sorted(self.sync, key=self.priority):
                    state = self.sync[key]
                    if running >= 5:
                        break
                    if not state.pending or state.task is not None or state.due > now:
                        continue
                    bg = state.refresh and self.priority(key)[0] > 0
                    if bg and background >= 3:
                        continue
                    state.background = bg
                    state.task = asyncio.create_task(self._execute(key))
                    running += 1
                    background += int(bg)
                if initial_only and not running and all(not s.pending or s.alert for s in self.sync.values()):
                    return
                await asyncio.sleep(0.1)
        finally:
            tasks = [s.task for s in self.sync.values() if s.task is not None] + list(self.retired_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for state in self.sync.values():
                state.task = None

    async def reconcile(self):
        await self.scheduler(initial_only=True)

    async def run(self):
        async with asyncio.TaskGroup() as group:
            group.create_task(self.quotes.run())
            group.create_task(self.scheduler())

    def status(self, symbol, now):
        if self.broker is None:
            checks = self.validate(symbol, now)
            completed = [tf for tf, check in checks.items() if check['complete']]
            errors = [f"{tf}: {error}" for tf, check in checks.items() for error in check['errors']]
        else:
            completed = [tf for tf in PHASES if self.window_ready(symbol, tf, now)]
            errors = [f"{tf}: {self.sync[symbol, tf].error}" for tf in PHASES if self.sync[symbol, tf].alert]
            for tf in PHASES:
                batch = self.store.batch(symbol, tf)
                if batch and batch.get('rejected'):
                    errors.extend(f"{tf} history: {row['ts']}: {row['error']}" for row in batch['rejected'])
            if self.quotes:
                errors.extend(f'{tf} live: {error}' for (s, tf), error in self.quotes.candle_errors.items() if s == symbol)
        level = 'full' if len(completed) == len(PHASES) else 'basic' if all(tf in completed for tf in ('1d', '5m')) else 'loading'
        refreshing = self.broker is not None and any(
            (self.sync[symbol, tf].refresh or self.sync[symbol, tf].loading) and self.store.batch(symbol, tf)
            for tf in PHASES)
        return {'stage': level, 'errors': errors, 'refreshing': bool(refreshing)}

    def quote(self, symbol, now):
        result = self.quotes.output(symbol, now) if self.quotes else {
            'symbol': symbol, 'regular': None, 'extended': {}, 'latest': None,
            'connection_health': 'DISCONNECTED', 'error': None}
        regular = result['regular']
        if regular and self.window_ready(symbol, '1d', now):
            day = datetime.fromtimestamp(regular['timestamp'], ET).date()
            previous = next((b['close'] for b in reversed(self.charts.closed(symbol, '1d')[1])
                             if datetime.fromtimestamp(b['time'], ET).date() < day), None)
            result['regular'] = {**regular, 'prev_close': previous or regular.get('prev_close')}
            if result['latest'] is regular:
                result['latest'] = result['regular']
        return result

    def view(self, symbol, tf, revisions=None, source='watchlist'):
        self.store.check(symbol)
        if tf not in INTRADAY:
            raise ValueError('Invalid chart timeframe')
        now = int(self.now())
        charts = {}
        for period in ('1d', tf):
            charts[period] = self.charts.chart(symbol, period, now,
                known_revision=None if revisions is None else revisions.get(period))
        status = self.status(symbol, now)
        return {'symbol': symbol, 'timeframe': tf, 'server_time': now, 'run_id': self.run_id, 'mode': self.mode,
                'charts': charts, 'quote': self.quote(symbol, now), 'status': status,
                'summary': self.charts.summary(symbol, now)}

    def board(self):
        now = int(self.now())
        pins = {ticker: index for index, ticker in enumerate(self.workspace.data['pinned'])} if self.workspace else {}
        result = []
        for ticker in self.tickers:
            state = self.status(ticker.symbol, now)
            member = self.workspace.data['statuses'].get(ticker.ticker, {}) if self.workspace else {}
            result.append({**member, **asdict(ticker), 'quote': self.quote(ticker.symbol, now),
                           **({'pinned': ticker.ticker in pins, 'pin_index': pins.get(ticker.ticker)} if self.workspace else {}),
                           'errors': state['errors']})
        return result

    async def api(self, path: str, query: dict):
        now = int(self.now())
        symbol = query.get('symbol', [None])[0]
        if symbol is not None:
            self.store.check(symbol)
        symbols = [symbol] if symbol else self.symbols
        if path == '/health':
            return {'service': 'running', 'mode': self.mode, 'started_at': self.started_at,
                    'universe_count': len(self.symbols),
                    'quote_health': self.quotes.connection_health if self.quotes else 'DISCONNECTED',
                    'quote_push_count': self.quotes.push_count if self.quotes else 0,
                    'pending': sum(s.pending for s in self.sync.values()),
                    'errors': {'/'.join(key): s.error for key, s in self.sync.items() if s.alert}}
        if path == '/v1/universe':
            return [asdict(ticker) for ticker in self.tickers]
        if path == '/v1/quotes':
            return [self.quote(s, now) for s in symbols]
        if path == '/v1/readiness':
            return {s: {'status': self.status(s, now), 'timeframes': self.validate(s, now)} for s in symbols}
        if path == '/v1/chart':
            if symbol is None:
                raise ValueError('symbol is required')
            tf = query.get('timeframe', ['5m'])[0]
            return self.view(symbol, tf)
        if path == '/v1/bars':
            if symbol is None:
                raise ValueError('symbol is required')
            tf = query.get('timeframe', ['5m'])[0]
            if tf not in PHASES:
                raise ValueError('timeframe must be ' + ', '.join(PHASES))
            return {'symbol': symbol, 'timeframe': tf, 'adjust_type': 'ForwardAdjust',
                    'session': 'regular', 'closed_only': True,
                    'current': self.window_ready(symbol, tf, now),
                    'bars': self.charts.closed(symbol, tf)[1]}
        raise KeyError(path)
