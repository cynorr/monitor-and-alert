"""One candle view: today's SDK values, overlaid by authoritative closed history."""
from __future__ import annotations

import time
from datetime import datetime

from .calendar import ET
from .indicators import series, preview, daily_summary, turnover_context, turnover_comparison
from .storage import Bar, bar_row


class ChartCache:
    def __init__(self, store, calendar, clock=time.time):
        self.store, self.calendar, self.now = store, calendar, clock
        self.live, self.live_revisions = {}, {}
        self.history, self.dependencies, self.summaries = {}, {}, {}

    def apply_candle(self, symbol, tf, row):
        return self.apply_candles(symbol, tf, [row])

    def apply_candles(self, symbol, tf, rows, *, replace=False):
        key, now = (symbol, tf), int(self.now())
        previous = self.live.get(key, {})
        incoming = {row['time']: row for row in rows}
        updated = incoming if replace else previous | incoming
        if updated == previous:
            return False
        self.live[key] = updated
        closed_before = {ts: row for ts, row in previous.items() if self.calendar.bar_end(ts, tf) <= now}
        closed_after = {ts: row for ts, row in updated.items() if self.calendar.bar_end(ts, tf) <= now}
        if closed_before != closed_after:
            self.live_revisions[key] = self.live_revisions.get(key, 0) + 1
        return True

    def new_day(self):
        self.live.clear()
        self.live_revisions.clear()
        self.dependencies.clear()

    def remove(self, symbol):
        for cache in (self.live, self.live_revisions, self.history, self.dependencies, self.summaries):
            for key in list(cache):
                if key == symbol or isinstance(key, tuple) and key[0] == symbol:
                    cache.pop(key)

    def closed(self, symbol, tf):
        key, now = (symbol, tf), int(self.now())
        target = self.calendar.latest_closed(tf, now)
        dependency = self.store.revisions.get(key, 0), self.live_revisions.get(key, 0), target
        if self.dependencies.get(key) != dependency:
            today = datetime.fromtimestamp(now, ET).date()
            merged = {ts: row for ts, row in self.live.get(key, {}).items()
                      if datetime.fromtimestamp(ts, ET).date() == today and self.calendar.bar_end(ts, tf) <= now}
            merged.update((bar.ts, bar_row(bar)) for bar in self.store.window(symbol, tf))
            rows = [dict(merged[ts]) for ts in sorted(merged)]
            amounts = turnover_context(rows, tf)
            for row in rows:
                row['turnover_comparison'] = turnover_comparison(row, tf, self.calendar, amounts)
            previous = self.history.get(key)
            if previous is None or previous[1] != rows:
                revision = previous[0] + 1 if previous else 1
                base = series(rows, sma_period=50 if tf == '1d' else 65)
                base['turnover_context'] = amounts
                bars = [Bar(symbol, tf, row['time'], row['open'], row['high'], row['low'],
                            row['close'], row['volume'], row.get('turnover')) for row in rows]
                self.history[key] = revision, rows, base, bars
            self.dependencies[key] = dependency
        return self.history[key]

    def forming(self, symbol, tf, now):
        start = self.calendar.active_start(tf, now)
        row = self.live.get((symbol, tf), {}).get(start)
        return {**row, 'provisional': True} if row is not None else None

    def chart(self, symbol, tf, now, known_revision=None):
        revision, rows, base, _ = self.closed(symbol, tf)
        active = self.forming(symbol, tf, now)
        if active:
            active['turnover_comparison'] = turnover_comparison(active, tf, self.calendar, base['turnover_context'])
        result = {'symbol': symbol, 'timeframe': tf, 'revision': revision,
                  'active': active, 'indicator_preview': preview(base, active)}
        if known_revision != revision:
            result.update(bars=rows, indicators=base['series'])
        return result

    def summary(self, symbol, now):
        revision, _, _, bars = self.closed(symbol, '1d')
        key = revision, self.calendar.latest_closed('1d', now)
        if symbol not in self.summaries or self.summaries[symbol][0] != key:
            self.summaries[symbol] = key, daily_summary(bars, self.calendar, now)
        return self.summaries[symbol][1]
