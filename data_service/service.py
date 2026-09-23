from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .calendar import ET, PHASES, INTRADAY, TradingCalendar
from .charts import ChartCache, bar_row
from .downloader import BarDownloader
from .quotes import QuoteService
from .store import BarStore
from .validator import DataValidator


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


class DataService:
    def __init__(self, tickers, runtime: Path, broker=None, calendar=None, clock=None):
        self.tickers = tickers
        self.symbols = [t.symbol for t in tickers]
        self.runtime, self.broker = runtime, broker
        self.now = clock or time.time
        self.mode = 'live'
        self.calendar = calendar or TradingCalendar()
        self.store = BarStore(runtime / 'bars.sqlite3', self.calendar, set(self.symbols))
        self.validator = DataValidator(self.store, self.calendar)
        self.charts = ChartCache(self.store, self.calendar)
        self.downloader = BarDownloader(broker, self.store, self.calendar, clock=self.now) if broker else None
        self.quotes = QuoteService(broker, self.symbols, self.calendar, on_quote=self.charts.apply_quote,
                                   on_reconnect=self.recover) if broker else None
        self.run_id = uuid.uuid4().hex
        self.started_at = int(self.now())
        self.focus = (self.symbols[0], '5m')
        self.sync = {(symbol, tf): SyncState() for symbol in self.symbols for tf in PHASES}

    def validate(self, symbol, now=None):
        return self.validator.validate(symbol, int(self.now()) if now is None else now)

    def select(self, symbol, timeframe):
        self.store.check(symbol)
        if timeframe not in INTRADAY:
            raise ValueError('Invalid intraday timeframe')
        self.focus = (symbol, timeframe)

    def recover(self):
        # A recovery cannot attribute missed Quote increments to the active bucket.
        self.charts.volume_baselines.clear()
        self.charts.quotes.clear()
        for active in self.charts.active.values():
            active['volume'] = None
        for state in self.sync.values():
            state.pending = state.refresh = True
            state.complete = False
            state.due = state.attempt = 0
            state.limit = 4

    def priority(self, key):
        symbol, tf = key
        state = self.sync[key]
        selected = symbol == self.focus[0]
        if not state.refresh:
            return (-2 if selected else -1, 0)
        if selected and tf in ('5m', '1d', self.focus[1]):
            return (0, ('5m', '1d', '15m', '30m', '1h').index(tf))
        return (('5m', '1d', '15m', '30m', '1h').index(tf) + 1, self.symbols.index(symbol))

    async def _execute(self, key):
        state = self.sync[key]
        count = 1000 if state.refresh else 2
        state.refresh = False
        try:
            await self.downloader.fetch(*key, count=count, background=state.background)
            check = self.validator.check(*key, int(self.now()))
            if not check['complete']:
                raise ValueError('; '.join(check['errors']))
        except sqlite3.Error:
            raise
        except Exception as exc:
            state.error = str(exc)
            state.complete = False
            state.refresh = state.pending = True
            state.attempt += 1
            if state.attempt >= state.limit:
                state.alert = True
                state.attempt, state.limit = 0, 3
                state.due = self.calendar.next_close('5m', int(self.now())) + 2
            else:
                state.due = self.now() + (2, 5, 10)[state.attempt - 1]
        else:
            state.complete = not state.refresh  # A recovery may have arrived while this request was in flight.
            state.pending = state.refresh
            state.target = check['target']
            state.error, state.alert = None, False
            state.attempt, state.limit, state.due = 0, 4, 0

    def _schedule(self, now):
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
            tasks = [s.task for s in self.sync.values() if s.task is not None]
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
            completed = [tf for tf in PHASES if self.sync[symbol, tf].complete]
            errors = [f"{tf}: {self.sync[symbol, tf].error}" for tf in PHASES if self.sync[symbol, tf].alert]
        level = 'full' if len(completed) == len(PHASES) else 'basic' if all(tf in completed for tf in ('1d', '5m')) else 'loading'
        return {'stage': level, 'errors': errors}

    def quote(self, symbol, now):
        result = self.quotes.output(symbol, now) if self.quotes else {
            'symbol': symbol, 'regular': None, 'extended': {}, 'connection_health': 'DISCONNECTED', 'error': None}
        regular = result['regular']
        if regular:
            day = datetime.fromtimestamp(regular['timestamp'], ET).date()
            previous = next((b['close'] for b in reversed(self.charts.closed(symbol, '1d')[1])
                             if datetime.fromtimestamp(b['time'], ET).date() < day), None)
            result['regular'] = {**regular, 'prev_close': previous or regular.get('prev_close')}
        return result

    def view(self, symbol, tf, revisions=None):
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
        result = []
        for ticker in self.tickers:
            state = self.status(ticker.symbol, now)
            result.append({**asdict(ticker), 'quote': self.quote(ticker.symbol, now),
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
                raise ValueError('timeframe must be 1d, 5m, 15m, 30m or 1h')
            limit = int(query.get('limit', ['1000'])[0])
            if not 1 <= limit <= 10000:
                raise ValueError('limit must be 1..10000')
            start, end = int(query.get('from', ['0'])[0]), int(query.get('to', [str(now)])[0])
            if start > end:
                raise ValueError('from must not exceed to')
            return {'symbol': symbol, 'timeframe': tf, 'adjust_type': 'NoAdjust',
                    'session': 'regular', 'closed_only': True,
                    'bars': [bar_row(b) for b in self.store.bars(symbol, tf, start, end, limit)]}
        raise KeyError(path)
