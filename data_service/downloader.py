from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime

from .calendar import ET, TradingCalendar, timestamp
from .store import Bar, BarStore

log = logging.getLogger(__name__)


def sdk_timestamp(value: datetime) -> int:
    # SDK naive datetimes represent machine-local time, including its DST offset.
    return timestamp(value.astimezone())


class BarDownloader:
    def __init__(self, broker, store: BarStore, calendar: TradingCalendar, clock=None):
        self.broker, self.store, self.calendar = broker, store, calendar
        self.now = clock or time.time

    def _parse(self, raw, symbol, timeframe, as_of):
        bars, rejected, forming, seen, anomalies = [], [], 0, set(), []
        for item in raw:
            ts = None
            try:
                ts = sdk_timestamp(item.timestamp)
                session = str(item.trade_session).split('.')[-1]
                if session not in {'Intraday', 'Normal'}:
                    raise ValueError('Non-regular candle returned')
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
                if bar.invalid_range:
                    anomalies.append({'symbol': symbol, 'timeframe': timeframe, 'session': session,
                        'start': ts, 'end': end,
                        'start_et': datetime.fromtimestamp(ts, ET).isoformat(),
                        'end_et': datetime.fromtimestamp(end, ET).isoformat(),
                        'fetched_at': as_of, 'fetched_at_et': datetime.fromtimestamp(as_of, ET).isoformat(),
                        'ohlcv': {k: str(getattr(item, k)) for k in ('open', 'high', 'low', 'close', 'volume')}})
            except (AttributeError, ValueError, TypeError, OverflowError) as exc:
                rejected.append({'ts': ts, 'error': str(exc)})
        if anomalies:
            try:
                with (self.store.path.parent / 'invalid_ohlc.jsonl').open('a') as file:
                    for anomaly in anomalies:
                        file.write(json.dumps(anomaly, allow_nan=False) + '\n')
            except OSError as exc:
                log.warning('Could not append OHLC comparison log: %s', exc)
        invalid_ts = {r['ts'] for r in rejected}
        return sorted((b for b in bars if b.ts not in invalid_ts), key=lambda b: b.ts), rejected, forming

    async def fetch(self, symbol: str, timeframe: str, count: int = 1000, *, background=False) -> dict:
        self.store.check(symbol)
        raw = await self.broker.candles(symbol, timeframe, count, background=background)
        as_of = int(self.now())
        bars, rejected, forming = self._parse(raw, symbol, timeframe, as_of)
        previous = self.store.batch(symbol, timeframe) or {}
        bounds = [b.ts for b in bars] + [r['ts'] for r in rejected if r['ts'] is not None and r['ts'] <= as_of]
        # A full recent response defines a NEW window. Older disconnected history is irrelevant.
        start = min(bounds) if bounds else self.calendar.latest_closed(timeframe, as_of)
        if count != 1000:
            start = previous.get('window_start', start)
            replaced = {b.ts for b in bars} | {r['ts'] for r in rejected}
            rejected = [r for r in previous.get('rejected', []) if r['ts'] not in replaced] + rejected
        batch = {'symbol': symbol, 'timeframe': timeframe, 'as_of': as_of,
                 'window_start': start, 'requested_count': count, 'returned_count': len(raw),
                 'forming_count': forming, 'rejected': rejected}
        self.store.upsert(bars, as_of, batch)
        return batch
