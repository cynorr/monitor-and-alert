"""Read-only volume intervals, using the largest complete official bars first."""
from datetime import datetime

from ..calendar import ET

PERIODS = ('2h', '1h', '30m', '15m', '5m')


class VolumeHistory:
    def __init__(self, charts):
        self.charts, self.calendar = charts, charts.calendar
        self.cache = {}

    def rows(self, symbol):
        windows = {tf: self.charts.closed(symbol, tf) for tf in PERIODS}
        signature = tuple(window[0] for window in windows.values())
        cached = self.cache.get(symbol)
        if cached is None or cached[0] != signature:
            rows = {tf: {row['time']: row['volume'] for row in window[1]} for tf, window in windows.items()}
            self.cache[symbol] = signature, rows
        return self.cache[symbol][1]

    def cover(self, symbol, start, end):
        """Cover [start, end) once. A gap is unavailable, never zero volume.

        This calculates a scalar only; it does not rebuild or persist candles.
        """
        rows, cursor, total = self.rows(symbol), start, 0
        while cursor < end:
            for tf in PERIODS:
                volume = rows[tf].get(cursor)
                if volume is not None:
                    close = self.calendar.bar_end(cursor, tf)
                    if close <= end:
                        total += volume
                        cursor = close
                        break
            else:
                return None
        return total

    def historical(self, symbol, start, end):
        """Interpolate only the last historical 5m slot, not today's volume."""
        if start == end:
            return 0
        day = datetime.fromtimestamp(end, ET).date()
        session = self.calendar.session(day)
        if not session or end > session[1]:
            return None
        if end == session[1]:
            return self.cover(symbol, start, end)
        tail = self.calendar.active_start('5m', end)
        total = self.cover(symbol, start, tail)
        if total is None or tail == end:
            return total
        volume = self.rows(symbol)['5m'].get(tail)
        close = self.calendar.bar_end(tail, '5m')
        return None if volume is None else total + volume * (end - tail) / (close - tail)

    def comparison(self, symbol, day, start_offset, end_offset, actual):
        samples = []
        for previous in self.calendar.previous_days(day):
            opened, _ = self.calendar.session(previous)
            value = self.historical(symbol, opened + start_offset, opened + end_offset)
            if value is not None:
                samples.append(value)
        average = sum(samples) / len(samples) if samples else None
        return {'ratio': actual / average if actual is not None and average else None,
                'actual': actual, 'average': average, 'samples': len(samples)}

    def current(self, symbol, now):
        day = datetime.fromtimestamp(now, ET).date()
        opened, _ = self.calendar.session(day)
        five = self.calendar.active_start('5m', now)
        active = self.charts.forming(symbol, '5m', now)
        prefix = self.cover(symbol, opened, five)
        actual = prefix + active['volume'] if prefix is not None and active else None
        cumulative = self.comparison(symbol, day, 0, now - opened, actual)
        tf = '5m' if now - opened < 900 else '15m'
        start = self.calendar.active_start(tf, now)
        local = self.charts.forming(symbol, tf, now)
        comparison = self.comparison(symbol, day, start - opened, now - opened,
                                     local['volume'] if local else None)
        return cumulative, {**comparison, 'window': tf}
