from __future__ import annotations

import logging
import math
import time
from datetime import datetime

from .calendar import TradingCalendar, timestamp
from .store import Bar, BarStore

log = logging.getLogger(__name__)


def sdk_timestamp(value: datetime) -> int:
    # SDK 5 returns naive machine-local datetimes. astimezone resolves the DST
    # offset at the actual instant; never label these naive values as UTC.
    return timestamp(value.astimezone())


class BarDownloader:
    def __init__(self, broker, store: BarStore, calendar: TradingCalendar, clock=None):
        self.broker, self.store, self.calendar = broker, store, calendar
        self.now = clock or (lambda: time.time())

    def _parse(self, raw, symbol, timeframe, as_of):
        bars, rejected, forming, seen = [], [], 0, set()
        for item in raw:
            ts = None
            try:
                ts = sdk_timestamp(item.timestamp)
                if str(item.trade_session).split('.')[-1] not in {'Intraday', 'Normal'}:
                    raise ValueError('Non-regular candle returned by Intraday request')
                end = self.calendar.bar_end(ts, timeframe)
                if ts in seen:
                    raise ValueError('Duplicate timestamp in API response')
                seen.add(ts)
                if end > as_of:
                    forming += 1
                    continue
                try:
                    turnover = float(item.turnover)
                    if not math.isfinite(turnover) or turnover < 0:
                        turnover = None
                except (AttributeError, TypeError, ValueError, OverflowError):
                    turnover = None
                bar = Bar(symbol, timeframe, ts, float(item.open), float(item.high),
                          float(item.low), float(item.close), item.volume, turnover)
                bar.validate(self.calendar, as_of)
                bars.append(bar)
            except (ValueError, TypeError, OverflowError) as exc:
                rejected.append({'ts': ts, 'error': str(exc),
                                 'ohlcv': {k: str(getattr(item, k, None))
                                           for k in ('open', 'high', 'low', 'close', 'volume')}})
        # A duplicate/invalid revision must not retain another row at the same timestamp.
        invalid_ts = {r['ts'] for r in rejected}
        return [b for b in bars if b.ts not in invalid_ts], rejected, forming

    async def fetch(self, symbol: str, timeframe: str, count: int = 1000,
                    run_id: str | None = None, before: int | None = None,
                    now: int | None = None) -> dict:
        self.store.check(symbol)
        raw = await self.broker.candles(symbol, timeframe, count, before)
        as_of = int(self.now()) if now is None else now
        bars, rejected, forming = self._parse(raw, symbol, timeframe, as_of)
        recovered = []
        # Bounded, nonrecursive repair using the same official source and validation.
        # Query backwards from the next boundary; count=2 also covers an inclusive
        # response containing the following candle. Accept only the exact target.
        candidates = [r for r in rejected if r['error'] == 'Invalid OHLC range'][:10]
        for rejection in candidates:
            ts = rejection['ts']
            try:
                boundary = ts + 86400 if timeframe == '1d' else self.calendar.bar_end(ts, timeframe)
                retry = await self.broker.candles(symbol, timeframe, 2, boundary)
                valid, _, _ = self._parse(retry, symbol, timeframe, as_of)
            except Exception as exc:
                rejection['repair_error'] = type(exc).__name__
                continue
            replacement = next((b for b in valid if b.ts == ts), None)
            if replacement is not None:
                bars.append(replacement)
                rejected.remove(rejection)
                recovered.append(rejection)
        bars.sort(key=lambda b: b.ts)
        batch = {'symbol': symbol, 'timeframe': timeframe, 'run_id': run_id,
                 'as_of': as_of, 'requested_count': count, 'returned_count': len(raw),
                 'returned_closed_ts': [b.ts for b in bars], 'forming_count': forming,
                 'rejected': rejected, 'recovered': recovered}
        previous = self.store.batch(symbol, timeframe)
        if run_id is None and previous:
            valid_ts = {b.ts for b in bars}
            previous['rejected'] = [r for r in previous['rejected'] if r['ts'] not in valid_ts]
            previous['rejected'] = [r for r in previous['rejected']
                                    if r['ts'] not in {r['ts'] for r in rejected}] + rejected
            previous['as_of'] = as_of
            previous['recovered'] = recovered
        self.store.upsert(bars, as_of, batch if run_id is not None else previous)
        if rejected:
            log.warning('Quarantined invalid bars %s %s count=%d first=%s', symbol, timeframe,
                        len(rejected), rejected[0])
        return batch

    async def confirm_short_history(self, symbol: str, batch: dict):
        starts = batch['returned_closed_ts']
        if batch['rejected'] or not starts:
            return
        first = min(starts)
        if batch['returned_count'] == 1000:
            return
        earlier = await self.broker.candles(symbol, '1d', 1, first - 60)
        existing = self.store.metadata(symbol)
        existing.update(first_daily_ts=first, history_exhausted=not earlier,
                        checked_at=batch['as_of'], source='longbridge_history_offset')
        self.store.set_metadata(symbol, existing)
