"""Memory-only display candles and indicator caches; never writes market bars."""
from __future__ import annotations

from datetime import datetime

from .calendar import ET
from .indicators import series, preview, daily_summary
from .resample import resample


def bar_row(bar):
    return {'time': bar.ts, 'open': bar.open, 'high': bar.high, 'low': bar.low,
            'close': bar.close, 'volume': bar.volume, 'turnover': bar.turnover}


class ChartCache:
    def __init__(self, store, calendar):
        self.store, self.calendar = store, calendar
        self.active, self.quotes, self.history, self.dependencies, self.summaries = {}, {}, {}, {}, {}
        self.volume_baselines, self.volume_prefixes = {}, {}

    def apply_quote(self, symbol, quote):
        if quote['trade_session'] != 'Intraday':
            return
        ts, price = quote['timestamp'], quote['last_price']
        start = self.calendar.active_start('5m', ts)
        if start is None or self.quotes.get(symbol, {}).get('timestamp', 0) > ts:
            return
        previous = self.quotes.get(symbol)
        self.quotes[symbol] = quote
        old = self.active.get(symbol)
        if old is None or old['time'] != start:
            self.active[symbol] = {'time': start, 'open': price, 'high': price, 'low': price, 'close': price, 'volume': None}
            # Compare Quote to Quote, never the day total to historical candle volume.
            # A missed bucket or mid-bucket startup has no trustworthy starting counter.
            self.volume_baselines[symbol] = (previous['cumulative_volume'] if previous
                and start - 300 <= previous['timestamp'] < start else None)
        else:
            old.update(high=max(old['high'], price), low=min(old['low'], price), close=price)
        if previous and quote['cumulative_volume'] < previous['cumulative_volume']:
            self.volume_baselines[symbol] = None
        baseline = self.volume_baselines.get(symbol)
        self.active[symbol]['volume'] = None if baseline is None else quote['cumulative_volume'] - baseline

    def closed(self, symbol, tf):
        key = (symbol, tf)
        source_periods = ('5m',) if tf in ('2h', '4h') else (tf, '5m') if tf not in ('1d', '5m') else (tf,)
        dependency = tuple((self.store.revisions.get((symbol, period), 0),
                            (self.store.batch(symbol, period) or {}).get('window_start', 0)) for period in source_periods)
        if self.dependencies.get(key) != dependency:
            bars = [] if tf in ('2h', '4h') else self.store.window(symbol, tf)
            rows = [bar_row(b) for b in bars]
            if tf not in ('1d', '5m'):
                five = self.closed(symbol, '5m')[1]
                # Inputs are official closed 5m bars; the final 5m end is the conversion cutoff.
                cutoff = self.calendar.bar_end(five[-1]['time'], '5m') if five else 0
                converted = resample(five, tf, self.calendar, cutoff)
                merged = {row['time']: row for row in converted}
                merged.update({row['time']: row for row in rows})
                rows = [merged[t] for t in sorted(merged)][-1000:]
            previous = self.history.get(key)
            if previous is None or previous[1] != rows:
                revision = previous[0] + 1 if previous else 1
                self.history[key] = (revision, rows, series(rows, sma_period=50 if tf == '1d' else 65), bars)
            self.dependencies[key] = dependency
        return self.history[key]

    def forming(self, symbol, tf, now):
        start = self.calendar.active_start(tf, now)
        five_start = self.calendar.active_start('5m', now)
        active, quote = self.active.get(symbol), self.quotes.get(symbol)
        if start is None or active is None or quote is None or active['time'] != five_start:
            return None
        day = datetime.fromtimestamp(now, ET).date()
        opened = self.calendar.session(day)[0]
        prefix = [b for b in self.closed(symbol, '5m')[1] if opened <= b['time'] < five_start]
        # Volume comes from the cached official prefix below; do not sum it in resample.
        pieces = [b for b in prefix if b['time'] >= start] + [{**active, 'volume': None}]
        candle = resample(pieces, tf, self.calendar, now, include_active=True)[-1]
        candle['volume'] = None
        if tf == '1d':
            candle['volume'] = quote['cumulative_volume']
        elif active['volume'] is not None:
            completed = self.closed_volume(symbol, tf, start, five_start)
            if completed is not None:
                candle['volume'] = completed + active['volume']
        return candle

    def closed_volume(self, symbol, tf, start, end):
        """Cached scalar for [start, end): cover once with the largest official bars."""
        periods = ('1h', '30m', '15m', '5m')
        signature = (start, end, tuple(self.store.revisions.get((symbol, p), 0) for p in periods))
        key = (symbol, tf)
        cached = self.volume_prefixes.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
        candidates = {}
        if start < end:
            for period in periods:
                for bar in self.store.bars(symbol, period, start, end - 1):
                    close = self.calendar.bar_end(bar.ts, period)
                    if close <= end:
                        candidates.setdefault(bar.ts, (close, bar.volume))
        cursor, total = start, 0
        while cursor < end:
            piece = candidates.get(cursor)
            if piece is None:
                total = None
                break
            cursor, volume = piece
            total += volume
        self.volume_prefixes[key] = (signature, total)
        return total

    def chart(self, symbol, tf, now, known_revision=None):
        revision, rows, base, _ = self.closed(symbol, tf)
        active = self.forming(symbol, tf, now)
        result = {'symbol': symbol, 'timeframe': tf, 'revision': revision,
                  'active': active, 'indicator_preview': preview(base, active)}
        if known_revision != revision:
            result.update(bars=rows, indicators=base['series'])
        return result

    def summary(self, symbol, now):
        revision, _, _, bars = self.closed(symbol, '1d')
        key = (revision, self.calendar.latest_closed('1d', now))
        if symbol not in self.summaries or self.summaries[symbol][0] != key:
            self.summaries[symbol] = (key, daily_summary(bars, self.calendar, now))
        return self.summaries[symbol][1]
