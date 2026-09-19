from __future__ import annotations

import logging
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
    def __init__(self, broker, store: BarStore, calendar: TradingCalendar):
        self.broker, self.store, self.calendar = broker, store, calendar

    async def fetch(self, symbol: str, timeframe: str, count: int = 1000,
                    run_id: str | None = None, before: int | None = None,
                    now: int | None = None) -> dict:
        self.store.check(symbol)
        raw = await self.broker.candles(symbol, timeframe, count, before)
        as_of = int(time.time()) if now is None else now
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
                bar = Bar(symbol, timeframe, ts, float(item.open), float(item.high),
                          float(item.low), float(item.close), item.volume)
                bar.validate(self.calendar, as_of)
                bars.append(bar)
            except (ValueError, TypeError, OverflowError) as exc:
                rejected.append({'ts': ts, 'error': str(exc),
                                 'ohlcv': {k: str(getattr(item, k, None))
                                           for k in ('open', 'high', 'low', 'close', 'volume')}})
        bars.sort(key=lambda b: b.ts)
        batch = {'symbol': symbol, 'timeframe': timeframe, 'run_id': run_id,
                 'as_of': as_of, 'requested_count': count, 'returned_count': len(raw),
                 'returned_closed_ts': [b.ts for b in bars], 'forming_count': forming,
                 'rejected': rejected}
        self.store.upsert(bars, as_of, batch if run_id is not None else None)
        if rejected:
            log.error('Rejected unexpected bars %s %s count=%d first=%s', symbol, timeframe,
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

    async def repair_ready_window(self, symbol: str, now: int):
        days = self.calendar.completed_days(now, 12)
        expected_first = self.calendar.grid(days[0], '5m')[0][0]
        existing = self.store.bars(symbol, '5m', expected_first)
        if not existing or existing[0].ts <= expected_first:
            return
        # At late intraday startup the latest 1000 can exclude the beginning
        # of day -12; a single targeted page recovers that omitted prefix.
        count = len(self.calendar.expected('5m', expected_first, existing[0].ts - 60, now))
        if not count:
            return
        original = self.store.batch(symbol, '5m')
        extra = await self.fetch(symbol, '5m', count=min(count, 1000), before=existing[0].ts - 60, now=now)
        if original:
            original['returned_closed_ts'] = sorted(set(original['returned_closed_ts']) | set(extra['returned_closed_ts']))
            original['rejected'].extend(extra['rejected'])
            original['supplemental_count'] = extra['returned_count']
            self.store.upsert([], now, original)
