"""Memory-only display candles and indicator caches; never writes market bars."""
from __future__ import annotations

from datetime import datetime

from .calendar import ET
from .indicators import series, preview, daily_summary


def bar_row(bar):
    return {'time': bar.ts, 'open': bar.open, 'high': bar.high, 'low': bar.low,
            'close': bar.close, 'volume': bar.volume, 'turnover': bar.turnover}


class ChartCache:
    def __init__(self, store, calendar):
        self.store, self.calendar = store, calendar
        self.active: dict[str, dict] = {}
        self.quotes: dict[str, dict] = {}
        self.history: dict[tuple, tuple] = {}
        self.summaries: dict[str, tuple] = {}

    def apply_quote(self, symbol, quote):
        if quote['trade_session'] != 'Intraday':
            return
        ts, price = quote['timestamp'], quote['last_price']
        start = self.calendar.active_start('5m', ts)
        if start is None:
            return
        old_quote = self.quotes.get(symbol)
        if old_quote and old_quote['timestamp'] > ts:
            return
        self.quotes[symbol] = quote
        old = self.active.get(symbol)
        if old is None or old['time'] != start:
            self.active[symbol] = {'time': start, 'open': price, 'high': price, 'low': price, 'close': price}
        else:
            old.update(high=max(old['high'], price), low=min(old['low'], price), close=price)

    def closed(self, symbol, tf):
        key = (symbol, tf)
        revision = self.store.revisions.get(key, 0)
        if key not in self.history or self.history[key][0] != revision:
            bars = self.store.bars(symbol, tf, limit=1000)
            rows = [bar_row(b) for b in bars]
            self.history[key] = (revision, rows, series(rows), bars)
        return self.history[key]

    def forming(self, symbol, tf, now):
        start = self.calendar.active_start(tf, now)
        five_start = self.calendar.active_start('5m', now)
        active, quote = self.active.get(symbol), self.quotes.get(symbol)
        if start is None or active is None or active['time'] != five_start:
            return None, []
        day = datetime.fromtimestamp(now, ET).date()
        if datetime.fromtimestamp(quote['timestamp'], ET).date() != day:
            return None, []
        five_rows = self.closed(symbol, '5m')[1]
        rejected = {r['ts'] for r in (self.store.batch(symbol, '5m') or {}).get('rejected', [])}
        # Exclude older sessions and the current incomplete bucket.
        opened = self.calendar.session(day)[0]
        prefix = [b for b in five_rows if opened <= b['time'] < five_start and b['time'] not in rejected]
        pieces = [b for b in prefix if b['time'] >= start] + [active]
        candle = {'time': start, 'open': pieces[0]['open'],
                  'high': max(p['high'] for p in pieces), 'low': min(p['low'] for p in pieces),
                  'close': quote['last_price'], 'volume': None, 'provisional': True}
        warnings = []
        if tf == '1d':
            candle['volume'] = quote['cumulative_volume']
        else:
            expected = {ts for ts, end in self.calendar.grid(day, '5m') if end <= start}
            before = [b for b in prefix if b['time'] < start]
            if {b['time'] for b in before} == expected:
                volume = quote['cumulative_volume'] - sum(b['volume'] for b in before)
                if volume >= 0:
                    candle['volume'] = volume
                else:
                    warnings.append('Live volume mismatch; waiting for synchronization')
        return candle, warnings

    def chart(self, symbol, tf, now, include_history=True):
        revision, rows, base, _ = self.closed(symbol, tf)
        active, warnings = self.forming(symbol, tf, now)
        result = {'symbol': symbol, 'timeframe': tf, 'revision': revision,
                  'active': active, 'indicator_preview': preview(base, active), 'warnings': warnings}
        if include_history:
            result.update(bars=rows, indicators=base['series'])
        return result

    def summary(self, symbol, now):
        revision, _, _, bars = self.closed(symbol, '1d')
        key = (revision, self.calendar.latest_closed('1d', now))
        if symbol not in self.summaries or self.summaries[symbol][0] != key:
            self.summaries[symbol] = (key, daily_summary(bars, self.calendar, now))
        return self.summaries[symbol][1]
