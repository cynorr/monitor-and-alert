from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .calendar import PHASES, TradingCalendar
from .downloader import BarDownloader
from .quotes import QuoteService
from .store import BarStore
from .validator import DataValidator

log = logging.getLogger(__name__)
RETRY_DELAYS = (2, 5, 10, 30)


class DataService:
    def __init__(self, tickers, runtime: Path, broker=None, calendar=None):
        self.tickers = tickers
        self.symbols = [ticker.symbol for ticker in tickers]
        self.runtime = runtime
        self.calendar = calendar or TradingCalendar()
        self.store = BarStore(runtime / 'bars.sqlite3', self.calendar, set(self.symbols))
        self.validator = DataValidator(self.store, self.calendar, runtime / 'data_ready.json')
        self.broker = broker
        self.downloader = BarDownloader(broker, self.store, self.calendar) if broker else None
        self.quotes = QuoteService(broker, self.symbols, self.calendar) if broker else None
        self.run_id = uuid.uuid4().hex
        self.phase = 'starting'
        self.errors = {}
        self.initialized = False
        self.started_at = int(time.time())
        self.retry_pairs: set[tuple[str, str]] = set()

    def validate(self, symbol: str, now: int | None = None, current_run=True):
        return self.validator.validate(symbol, int(time.time()) if now is None else now,
                                       self.run_id if current_run else None)

    async def _cold_fetch(self, symbol, timeframe):
        batch = await self.downloader.fetch(symbol, timeframe, run_id=self.run_id)
        if timeframe == '1d':
            await self.downloader.confirm_short_history(symbol, batch)
        if timeframe == '5m':
            await self.downloader.repair_ready_window(symbol, int(time.time()))
        if batch['rejected'] or not batch['returned_closed_ts']:
            raise ValueError('Batch has no valid closed bars or contains rejected bars')
        self.errors.pop(f'{symbol}/{timeframe}', None)

    async def reconcile(self):
        for symbol in self.symbols:
            self.validate(symbol)
        self.validator.save()
        for timeframe in PHASES:
            self.phase = f'cold_start:{timeframe}'
            log.info('Cold start phase %s', timeframe)
            for symbol in self.symbols:
                try:
                    await self._cold_fetch(symbol, timeframe)
                except sqlite3.Error:
                    raise
                except Exception as exc:
                    self.errors[f'{symbol}/{timeframe}'] = str(exc)
                    self.retry_pairs.add((symbol, timeframe))
                    log.warning('Download failed %s %s: %s', symbol, timeframe, exc)
                if timeframe in ('5m', '1h'):
                    state = self.validate(symbol)
                    if timeframe == '1h':
                        for check in state['ready_checks'] + state['full_checks']:
                            if not check.get('ok'):
                                self.retry_pairs.add((symbol, check['timeframe']))
                    self.validator.save()
        self.initialized = True
        self.phase = 'running'

    async def repair_initial(self):
        for attempt in range(3):
            if not self.retry_pairs:
                return
            await asyncio.sleep(RETRY_DELAYS[attempt])
            pending, self.retry_pairs = sorted(self.retry_pairs), set()
            log.warning('Repair pass %d pairs=%d', attempt + 1, len(pending))
            for symbol, timeframe in pending:
                try:
                    await self._cold_fetch(symbol, timeframe)
                except sqlite3.Error:
                    raise
                except Exception as exc:
                    self.errors[f'{symbol}/{timeframe}'] = str(exc)
                    self.retry_pairs.add((symbol, timeframe))
                state = self.validate(symbol)
                checks = [c for c in state['ready_checks'] + state['full_checks'] if c['timeframe'] == timeframe]
                if not all(c.get('ok') for c in checks):
                    self.retry_pairs.add((symbol, timeframe))
            self.validator.save()
        if self.retry_pairs:
            log.error('Repair exhausted for %d pairs; readiness remains unavailable where gaps exist', len(self.retry_pairs))

    async def update_bar(self, symbol, timeframe, target):
        previous = self.store.bars(symbol, timeframe, limit=1)
        missing = self.calendar.expected(timeframe, previous[0].ts + 1, target, int(time.time())) if previous else []
        count = 1000 if not previous or len(missing) > 1 else 2
        batch = await self.downloader.fetch(symbol, timeframe, count=count)
        found = self.store.bars(symbol, timeframe, target, target)
        if not found or batch['rejected']:
            raise ValueError(f'Expected closed bar not available: {target}')
        if len(missing) > 1:
            actual = {b.ts for b in self.store.bars(symbol, timeframe, missing[0], target)}
            unresolved = set(missing) - actual
            if unresolved:
                raise ValueError(f'Unrepaired gap after refresh: {len(unresolved)} bars')
        self.errors.pop(f'{symbol}/{timeframe}', None)
        self.validate(symbol)

    async def scheduler(self):
        pending = {}
        completed = {}
        last_day = None
        repairs = {key: [time.time() + 2, 0] for key in self.retry_pairs}
        while True:
            now = int(time.time())
            day = self.calendar.completed_days(now, 1)[-1]
            if day != last_day:
                for symbol in self.symbols:
                    self.validate(symbol, now)
                self.validator.save()
                last_day = day
            for timeframe in PHASES:
                target = self.calendar.latest_closed(timeframe, now)
                due = self.calendar.bar_end(target, timeframe) + 2
                for symbol in self.symbols:
                    key = (symbol, timeframe)
                    if key in pending or completed.get(key) == target:
                        continue
                    if self.store.bars(symbol, timeframe, target, target):
                        completed[key] = target
                    else:
                        pending[key] = [target, due, 0]
            due_jobs = [(key, value) for key, value in pending.items() if value[1] <= time.time()]
            for (symbol, timeframe), (target, due, attempt) in due_jobs:
                key = (symbol, timeframe)
                try:
                    await self.update_bar(symbol, timeframe, target)
                    completed[key] = target
                    del pending[key]
                except sqlite3.Error:
                    raise
                except Exception as exc:
                    self.errors[f'{symbol}/{timeframe}'] = str(exc)
                    if attempt < len(RETRY_DELAYS):
                        pending[key] = [target, time.time() + RETRY_DELAYS[attempt], attempt + 1]
                        log.warning('Bar retry %s %s target=%d: %s', symbol, timeframe, target, exc)
                    else:
                        completed[key] = target
                        del pending[key]
                        log.error('Bar retries exhausted %s %s target=%d: %s', symbol, timeframe, target, exc)
                        self.validate(symbol)
            repair_due = [key for key, (due, _) in repairs.items() if due <= time.time()]
            if repair_due:
                symbol, timeframe = key = sorted(repair_due)[0]
                _, attempt = repairs[key]
                try:
                    await self._cold_fetch(symbol, timeframe)
                except sqlite3.Error:
                    raise
                except Exception as exc:
                    self.errors[f'{symbol}/{timeframe}'] = str(exc)
                state = self.validate(symbol)
                checks = [c for c in state['ready_checks'] + state['full_checks'] if c['timeframe'] == timeframe]
                if all(c.get('ok') for c in checks):
                    self.retry_pairs.discard(key)
                    del repairs[key]
                elif attempt >= 2:
                    del repairs[key]
                    log.error('Initial repair exhausted %s %s', symbol, timeframe)
                else:
                    repairs[key] = [time.time() + RETRY_DELAYS[attempt + 1], attempt + 1]
            if due_jobs or repair_due:
                self.validator.save()
            else:
                await asyncio.sleep(1)

    async def run(self):
        async def history():
            await self.reconcile()
            await self.scheduler()
        async with asyncio.TaskGroup() as group:
            group.create_task(self.quotes.run())
            group.create_task(history())

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
            return [self.quotes.output(s, now) for s in symbols] if self.quotes else []
        if path == '/v1/readiness':
            # Recompute from SQLite; never trust the derived JSON file.
            for s in symbols:
                self.validate(s, now, current_run=self.broker is not None)
            return {s: self.validator.states[s] for s in symbols}
        if path == '/v1/bars':
            if symbol is None:
                raise ValueError('symbol is required')
            timeframe = query.get('timeframe', ['5m'])[0]
            if timeframe not in PHASES:
                raise ValueError('timeframe must be 1d, 5m, 15m, 30m or 1h')
            limit = int(query.get('limit', ['1000'])[0])
            if not 1 <= limit <= 10000:
                raise ValueError('limit must be 1..10000')
            start, end = int(query.get('from', ['0'])[0]), int(query.get('to', [str(now)])[0])
            if start > end:
                raise ValueError('from must not exceed to')
            bars = self.store.bars(symbol, timeframe, start, end, limit)
            return {'symbol': symbol, 'timeframe': timeframe, 'adjust_type': 'NoAdjust',
                    'session': 'regular', 'closed_only': True,
                    'bars': [{'time': b.ts, 'open': b.open, 'high': b.high, 'low': b.low,
                              'close': b.close, 'volume': b.volume} for b in bars]}
        raise KeyError(path)
