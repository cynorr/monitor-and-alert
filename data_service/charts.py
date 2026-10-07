"""Memory-only display candles and indicator caches; never writes market bars."""
from __future__ import annotations

from .indicators import series, preview, daily_summary, volume_context, volume_comparison


def bar_row(bar):
    return {'time': bar.ts, 'open': bar.open, 'high': bar.high, 'low': bar.low,
            'close': bar.close, 'volume': bar.volume, 'turnover': bar.turnover}


class ChartCache:
    def __init__(self, store, calendar, ready=None):
        self.store, self.calendar = store, calendar
        self.ready = ready or (lambda symbol, tf: True)
        self.active, self.history, self.dependencies, self.summaries = {}, {}, {}, {}
        self.views = {}

    def apply_candle(self, symbol, tf, row, *, initial=False):
        key = (symbol, tf)
        previous = self.active.get(key)
        # Subscription history can return after a newer push has already arrived.
        if previous and (previous['time'] > row['time'] or initial and previous['time'] == row['time']):
            return
        self.active[key] = row

    def closed(self, symbol, tf):
        key = (symbol, tf)
        dependency = self.store.revisions.get(key, 0)
        if self.dependencies.get(key) != dependency:
            bars = self.store.window(symbol, tf)
            rows = [bar_row(b) for b in bars]
            volume = volume_context(rows, tf)
            for row in rows:
                row['volume_comparison'] = volume_comparison(row, tf, self.calendar, volume)
            previous = self.history.get(key)
            if previous is None or previous[1] != rows:
                revision = previous[0] + 1 if previous else 1
                base = series(rows, sma_period=50 if tf == '1d' else 65)
                base['volume_context'] = volume
                self.history[key] = (revision, rows, base, bars)
            self.dependencies[key] = dependency
        return self.history[key]

    def forming(self, symbol, tf, now):
        active = self.active.get((symbol, tf))
        start = self.calendar.active_start(tf, now)
        if self.ready(symbol, tf) and start is not None and active and active['time'] == start:
            return {**active, 'provisional': True}
        return None

    def chart(self, symbol, tf, now, known_revision=None):
        key = (symbol, tf)
        previous = self.views.get(key)
        ready = self.ready(symbol, tf)
        revision, rows, base, _ = self.closed(symbol, tf)
        target = self.calendar.latest_closed(tf, now)
        closed_ready = bool(rows and rows[-1]['time'] == target)
        active = self.forming(symbol, tf, now) if ready and closed_ready else None
        if active:
            active['volume_comparison'] = volume_comparison(active, tf, self.calendar, base['volume_context'])
        # Publish a complete replacement only after this period's closed history
        # and next SDK candle are ready. Other periods do not block this chart.
        waiting = not ready or not closed_ready or (active is None and previous is not None
            and previous['active'] is not None
            and not any(row['time'] == previous['active']['time'] for row in rows))
        if waiting and previous is not None:
            full = previous
        else:
            full = {'symbol': symbol, 'timeframe': tf, 'revision': revision,
                    'bars': rows, 'indicators': base['series'],
                    'active': active, 'indicator_preview': preview(base, active)}
            self.views[key] = full
        result = {name: value for name, value in full.items() if name not in ('bars', 'indicators')}
        if known_revision != full['revision']:
            result.update(bars=full['bars'], indicators=full['indicators'])
        return result

    def summary(self, symbol, now):
        revision, _, _, bars = self.closed(symbol, '1d')
        key = (revision, self.calendar.latest_closed('1d', now))
        if symbol not in self.summaries or self.summaries[symbol][0] != key:
            self.summaries[symbol] = (key, daily_summary(bars, self.calendar, now))
        return self.summaries[symbol][1]
