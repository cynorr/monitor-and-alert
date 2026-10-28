"""Official candle conversion, history downloads and read-only window checks."""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime

from ..calendar import PHASES, TradingCalendar, timestamp
from ..storage import Bar, BarStore, ohlc_comparison, append_ohlc_log

log = logging.getLogger(__name__)


def sdk_timestamp(value: datetime) -> int:
    # SDK naive datetimes represent machine-local time, including its DST offset.
    return timestamp(value.astimezone())


def parse_candle(item, symbol, timeframe, calendar, as_of, *, closed=True):
    session = str(item.trade_session).split('.')[-1]
    if session not in {'Intraday', 'Normal'}:
        raise ValueError('Non-regular candle returned')
    try:
        turnover = float(item.turnover)
        if not math.isfinite(turnover) or turnover < 0:
            turnover = None
    except (AttributeError, TypeError, ValueError, OverflowError):
        turnover = None
    bar = Bar(symbol, timeframe, sdk_timestamp(item.timestamp), float(item.open), float(item.high),
              float(item.low), float(item.close), item.volume, turnover)
    bar.validate(calendar, as_of, closed=closed)
    return bar


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
                    bars = [bar for bar in bars if bar.ts != ts]
                    raise ValueError('Duplicate timestamp in API response')
                seen.add(ts)
                if end > as_of:
                    forming += 1
                    continue
                bar = parse_candle(item, symbol, timeframe, self.calendar, as_of)
                bars.append(bar)
                if bar.invalid_range:
                    anomalies.append(ohlc_comparison(bar, self.calendar, as_of, session,
                        {k: str(getattr(item, k)) for k in ('open', 'high', 'low', 'close', 'volume')}))
            except (AttributeError, ValueError, TypeError, OverflowError) as exc:
                rejected.append({'ts': ts, 'error': str(exc)})
        append_ohlc_log(self.store.path.parent / 'invalid_ohlc.jsonl', anomalies)
        return sorted(bars, key=lambda b: b.ts), rejected, forming

    async def fetch(self, symbol: str, timeframe: str, count: int = 1000, *, background=False) -> dict | None:
        self.store.check(symbol)
        session = self.calendar.window_session(int(self.now()))
        if count != 1000:
            batch = self.store.batch(symbol, timeframe)
            if batch is None or batch['session'][0] != session[0]:
                return None
        raw = await self.broker.candles(symbol, timeframe, count, background=background)
        as_of = int(self.now())
        if self.calendar.window_session(as_of)[0] != session[0]:
            return None
        bars, rejected, forming = self._parse(raw, symbol, timeframe, as_of)
        target = self.calendar.latest_closed(timeframe, as_of)
        if not any(bar.ts == target for bar in bars):
            details = '; '.join(f"{item['ts']}: {item['error']}" for item in rejected)
            raise ValueError(f'Missing latest closed {timeframe} bar: {target}' + (f'; {details}' if details else ''))
        if rejected:
            log.warning('%s %s rejected history rows: %s', symbol, timeframe, rejected)
        if count != 1000:
            rejected = batch.get('rejected', []) + rejected
        batch = {'symbol': symbol, 'timeframe': timeframe, 'as_of': as_of,
                 'session': session, 'requested_count': count, 'returned_count': len(raw),
                 'forming_count': forming, 'rejected': rejected}
        self.store.upsert(bars, as_of, batch, replace=count == 1000)
        return batch


class HistoryValidator:
    def __init__(self, store, calendar):
        self.store, self.calendar = store, calendar
        self.cache = {}

    def check(self, symbol, tf, now):
        target = self.calendar.latest_closed(tf, now)
        key = (symbol, tf)
        session = self.calendar.window_session(now)
        signature = (self.store.revisions.get(key, 0), target, session)
        if key in self.cache and self.cache[key][0] == signature:
            return self.cache[key][1]
        batch = self.store.batch(symbol, tf)
        rows = self.store.window(symbol, tf)
        present, errors = set(), []
        for row in rows:
            try:
                row.validate(self.calendar, now)
                present.add(row.ts)
            except ValueError as exc:
                errors.append(f'{row.ts}: {exc}')
        # Historical holes are accepted, including within the returned recent window.
        # Only the current closed target must exist; never bridge old gaps.
        missing = [] if target in present else [target]
        if batch and batch['session'][0] != session[0]:
            errors.append('Waiting for current trading-day refresh')
        if missing:
            errors.insert(0, f'Missing {len(missing)} bars; first timestamp {missing[0]}')
        result = {'complete': bool(batch) and not errors, 'target': target,
                  'latest': max(present) if present else None, 'count': len(present),
                  'missing': missing, 'errors': errors}
        self.cache[key] = (signature, result)
        return result

    def validate(self, symbol, now):
        return {tf: self.check(symbol, tf, now) for tf in PHASES}
