from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .calendar import PHASES, TradingCalendar
from .charts import ChartCache, bar_row
from .downloader import BarDownloader
from .quotes import QuoteService
from .store import BarStore
from .validator import DataValidator

log = logging.getLogger(__name__)
RETRY_DELAYS = (2, 5, 10, 30)


@dataclass
class Job:
    symbol: str
    timeframe: str
    initial: bool
    due: float = 0
    attempt: int = 0
    target: int | None = None


class DataService:
    def __init__(self, tickers, runtime: Path, broker=None, calendar=None):
        self.tickers = tickers
        self.symbols = [t.symbol for t in tickers]
        self.runtime, self.broker = runtime, broker
        self.calendar = calendar or TradingCalendar()
        self.store = BarStore(runtime / 'bars.sqlite3', self.calendar, set(self.symbols))
        self.validator = DataValidator(self.store, self.calendar, runtime / 'data_ready.json')
        self.charts = ChartCache(self.store, self.calendar)
        self.downloader = BarDownloader(broker, self.store, self.calendar) if broker else None
        self.quotes = QuoteService(broker, self.symbols, self.calendar, on_quote=self.charts.apply_quote) if broker else None
        self.run_id = uuid.uuid4().hex
        self.phase, self.initialized = 'starting', False
        self.started_at = int(time.time())
        self.errors = {}
        self.retry_pairs = set()
        self.focus = (self.symbols[0], '5m')
        self.jobs: dict[tuple, Job] = {}
        self.running: dict[tuple, asyncio.Task] = {}
        self.initial_done = set()
        self.ever_loaded = set()
        self.lag_targets = {}
        self.retry_after = {}

    def validate(self, symbol, now=None, current_run=True):
        return self.validator.validate(symbol, int(time.time()) if now is None else now,
                                       self.run_id if current_run else None)

    def select(self, symbol, timeframe):
        self.store.check(symbol)
        if timeframe not in PHASES or timeframe == '1d':
            raise ValueError('Intraday timeframe must be 5m, 15m, 30m or 1h')
        self.focus = (symbol, timeframe)

    def priority(self, job):
        if not job.initial:
            return (-2 if job.symbol == self.focus[0] else -1, 0)
        if job.symbol == self.focus[0] and job.timeframe in ('1d', '5m', self.focus[1]):
            return (0, ('5m', '1d', '15m', '30m', '1h').index(job.timeframe))
        return ({'5m': 1, '1d': 2, '15m': 3, '30m': 4, '1h': 5}[job.timeframe],
                self.symbols.index(job.symbol))

    async def _cold_fetch(self, symbol, timeframe):
        batch = await self.downloader.fetch(symbol, timeframe, run_id=self.run_id)
        if timeframe == '1d':
            await self.downloader.confirm_short_history(symbol, batch)
        state = self.validate(symbol)
        check = state['timeframes'][timeframe]
        if not check['ok']:
            raise ValueError(f'{timeframe}: historical range incomplete or invalid')
        self.errors.pop(f'{symbol}/{timeframe}', None)
        return batch

    async def update_bar(self, symbol, timeframe, target):
        previous = self.store.bars(symbol, timeframe, limit=1)
        now = int(time.time())
        missing = self.calendar.expected(timeframe, previous[0].ts + 1, target, now) if previous else []
        count = 1000 if not previous or len(missing) > 1 else 2
        batch = await self.downloader.fetch(symbol, timeframe, count=count)
        found = self.store.bars(symbol, timeframe, target, target)
        if not found or batch['rejected']:
            raise ValueError(f'Expected closed bar not available: {target}')
        if len(missing) > 1:
            actual = {b.ts for b in self.store.bars(symbol, timeframe, missing[0], target)}
            returned = batch['returned_closed_ts']
            cursor = min(returned) if returned else target
            while any(ts < cursor for ts in set(missing) - actual):
                prefix = [ts for ts in missing if ts < cursor and ts not in actual]
                extra = await self.downloader.fetch(symbol, timeframe, count=min(1000, len(prefix)),
                                                    before=cursor - 60)
                earlier = [ts for ts in extra['returned_closed_ts'] if ts < cursor]
                if not earlier or extra['rejected']:
                    break
                cursor = min(earlier)
                actual.update(earlier)
            if set(missing) - actual:
                raise ValueError('Unrepaired gap after refresh')
        self.errors.pop(f'{symbol}/{timeframe}', None)
        self.validate(symbol)

    async def _execute(self, key, job):
        try:
            if job.initial:
                await self._cold_fetch(*key)
            else:
                await self.update_bar(*key, job.target)
        except sqlite3.Error:
            raise
        except Exception as exc:
            self.errors['/'.join(key)] = str(exc)
            self.retry_pairs.add(key)
            if job.attempt < len(RETRY_DELAYS):
                job.due = time.time() + RETRY_DELAYS[job.attempt]
                job.attempt += 1
                return
            log.warning('History retry exhausted %s: %s', key, exc)
            self.retry_after[key] = time.time() + 30
        else:
            self.retry_pairs.discard(key)
            self.retry_after.pop(key, None)
            if self.validate(job.symbol)['timeframes'][job.timeframe]['loaded']:
                self.ever_loaded.add(key)
        if job.initial:
            self.initial_done.add(key)
        self.jobs.pop(key, None)

    def _schedule(self, now, initial_only=False):
        for tf in PHASES:
            target = self.calendar.latest_closed(tf, now)
            for symbol in self.symbols:
                key = (symbol, tf)
                if key not in self.initial_done:
                    self.jobs.setdefault(key, Job(*key, initial=True))
                    continue
                check = self.validate(symbol, now)['timeframes'][tf]
                if check['loaded']:
                    self.ever_loaded.add(key)
                if initial_only or key in self.jobs or now < self.retry_after.get(key, 0):
                    continue
                if not check['loaded']:
                    self.jobs[key] = Job(*key, initial=not check['synced'],
                                         target=target, due=self.calendar.bar_end(target, tf) + 2)

    async def scheduler(self, initial_only=False):
        last_save = 0
        try:
            while True:
                for key, task in list(self.running.items()):
                    if task.done():
                        task.result()
                        del self.running[key]
                now = int(time.time())
                self._schedule(now, initial_only=initial_only)
                for job in sorted(self.jobs.values(), key=self.priority):
                    key = (job.symbol, job.timeframe)
                    if len(self.running) >= 5:
                        break
                    if key not in self.running and job.due <= time.time():
                        self.running[key] = asyncio.create_task(self._execute(key, job))
                self.initialized = len(self.initial_done) == len(self.symbols) * len(PHASES)
                self.phase = 'running' if self.initialized else 'loading'
                if now - last_save >= 5:
                    for symbol in self.symbols:
                        self.validate(symbol, now)
                    self.validator.save()
                    last_save = now
                if initial_only and self.initialized and not self.running:
                    return
                await asyncio.sleep(0.1)
        finally:
            for task in self.running.values():
                task.cancel()
            await asyncio.gather(*self.running.values(), return_exceptions=True)
            self.running.clear()

    async def reconcile(self):
        await self.scheduler(initial_only=True)

    async def run(self):
        async with asyncio.TaskGroup() as group:
            group.create_task(self.quotes.run())
            group.create_task(self.scheduler())

    def status(self, symbol, now):
        state = self.validate(symbol, now, current_run=self.broker is not None)
        warnings = list(state['warnings'])
        for tf, check in state['timeframes'].items():
            key = (symbol, tf)
            if check['loaded']:
                self.ever_loaded.add(key)
                self.lag_targets.pop(key, None)
            elif key in self.ever_loaded:
                target = self.lag_targets.setdefault(key, check['target'])
                if now - self.calendar.bar_end(target, tf) > 15:
                    warnings.append(f'{tf}: 官方 K 线更新延迟超过 15 秒')
            error = self.errors.get(f'{symbol}/{tf}')
            if error:
                warnings.append(f'{tf}: {error}')
        summary = self.charts.summary(symbol, now)
        if summary['samples'] < 20:
            warnings.append(f"Daily: 20 日指标可用样本 {summary['samples']} 日")
        if summary['estimated']:
            warnings.append('20 日均额包含估算成交额')
        return {**state, 'warnings': list(dict.fromkeys(warnings))}

    def quote(self, symbol, now):
        return self.quotes.output(symbol, now) if self.quotes else {
            'symbol': symbol, 'regular': None, 'extended': {}, 'connection_health': 'OFFLINE', 'error': None}

    def view(self, symbol, tf, revisions=None):
        self.store.check(symbol)
        if tf not in ('5m', '15m', '30m', '1h'):
            raise ValueError('Invalid chart timeframe')
        now = int(time.time())
        charts = {}
        for period in ('1d', tf):
            rev = self.store.revisions.get((symbol, period), 0)
            include = revisions is None or revisions.get(period) != rev
            charts[period] = self.charts.chart(symbol, period, now, include)
        status = self.status(symbol, now)
        for chart in charts.values():
            status['warnings'].extend(chart['warnings'])
        return {'symbol': symbol, 'timeframe': tf, 'server_time': now, 'run_id': self.run_id,
                'charts': charts, 'quote': self.quote(symbol, now), 'status': status,
                'summary': self.charts.summary(symbol, now)}

    def board(self):
        now = int(time.time())
        result = []
        for ticker in self.tickers:
            state = self.status(ticker.symbol, now)
            result.append({**asdict(ticker), 'quote': self.quote(ticker.symbol, now),
                           'ready': state['ready'], 'full_ready': state['full_ready'],
                           'warnings': state['warnings']})
        return result

    async def api(self, path: str, query: dict):
        now = int(time.time())
        symbol = query.get('symbol', [None])[0]
        if symbol is not None:
            self.store.check(symbol)
        symbols = [symbol] if symbol else self.symbols
        if path == '/health':
            return {'service': 'running', 'phase': self.phase, 'initialized': self.initialized,
                    'started_at': self.started_at, 'universe_count': len(self.symbols),
                    'quote_health': self.quotes.connection_health if self.quotes else 'OFFLINE',
                    'last_quote_received_at': self.quotes.last_quote_received_at if self.quotes else None,
                    'quote_push_count': self.quotes.push_count if self.quotes else 0,
                    'history_errors': dict(self.errors), 'pending_repairs': len(self.retry_pairs)}
        if path == '/v1/universe':
            return [asdict(ticker) for ticker in self.tickers]
        if path == '/v1/quotes':
            return [self.quote(s, now) for s in symbols]
        if path == '/v1/readiness':
            return {s: self.status(s, now) for s in symbols}
        if path == '/v1/chart':
            if symbol is None:
                raise ValueError('symbol is required')
            tf = query.get('timeframe', ['5m'])[0]
            self.select(symbol, tf)
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
