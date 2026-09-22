"""One session-aligned OHLCV conversion for all display periods. Never writes bars."""
from collections import defaultdict
from datetime import datetime

from .calendar import ET


def resample(rows, timeframe, calendar, now, *, include_active=False):
    groups = defaultdict(list)
    for row in rows:
        start = calendar.active_start(timeframe, row['time'])
        if start is not None:
            groups[start].append(row)
    result = []
    for start, pieces in sorted(groups.items()):
        pieces.sort(key=lambda row: row['time'])
        end = calendar.bar_end(start, timeframe)
        active = end > now
        if active and not include_active:
            continue
        if not active:
            day = datetime.fromtimestamp(start, ET).date()
            expected = {ts for ts, _ in calendar.grid(day, '5m')
                        if (calendar.session(day)[0] if timeframe == '1d' else start) <= ts < end}
            if {p['time'] for p in pieces} != expected:
                continue
        row = {'time': start, 'open': pieces[0]['open'], 'high': max(p['high'] for p in pieces),
               'low': min(p['low'] for p in pieces), 'close': pieces[-1]['close'],
               'volume': sum(p['volume'] for p in pieces) if all(p.get('volume') is not None for p in pieces) else None,
               'turnover': sum(p['turnover'] for p in pieces) if all(p.get('turnover') is not None for p in pieces) else None}
        if active:
            row['provisional'] = True
        result.append(row)
    return result
