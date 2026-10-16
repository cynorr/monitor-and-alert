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


def ohlc_comparison(bar, calendar, as_of, session, ohlcv):
    end = calendar.bar_end(bar.ts, bar.timeframe)
    return {'symbol': bar.symbol, 'timeframe': bar.timeframe, 'session': session,
            'start': bar.ts, 'end': end,
            'start_et': datetime.fromtimestamp(bar.ts, ET).isoformat(),
            'end_et': datetime.fromtimestamp(end, ET).isoformat(),
            'fetched_at': as_of, 'fetched_at_et': datetime.fromtimestamp(as_of, ET).isoformat(),
            'ohlcv': ohlcv}


def append_ohlc_log(path, anomalies):
    if not anomalies:
        return
    try:
        with path.open('a') as file:
            for anomaly in anomalies:
                file.write(json.dumps(anomaly, allow_nan=False) + '\n')
    except OSError as exc:
        log.warning('Could not append OHLC comparison log: %s', exc)


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
            if batch is None or tuple(batch['session']) != session:
                return None
        raw = await self.broker.candles(symbol, timeframe, count, background=background)
        as_of = int(self.now())
        if self.calendar.window_session(as_of) != session:
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
