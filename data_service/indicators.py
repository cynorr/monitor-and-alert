"""Pure calculations. Live previews always start from closed-bar state."""
from __future__ import annotations

from datetime import datetime

from .calendar import ET


def series(rows: list[dict]) -> dict:
    result = {'ema10': [], 'ema20': [], 'sma50': []}
    previous = {10: None, 20: None}
    closes = []
    for row in rows:
        close = row['close']
        closes.append(close)
        for period in previous:
            alpha = 2 / (period + 1)
            value = close if previous[period] is None else alpha * close + (1 - alpha) * previous[period]
            previous[period] = value
            if len(closes) >= period:
                result[f'ema{period}'].append({'time': row['time'], 'value': value})
        if len(closes) >= 50:
            result['sma50'].append({'time': row['time'], 'value': sum(closes[-50:]) / 50})
    return {'series': result, 'ema': previous, 'tail': closes[-49:], 'count': len(closes)}


def preview(base: dict, active: dict | None) -> dict:
    if active is None:
        return {}
    close, count = active['close'], base['count'] + 1
    values = {}
    for period in (10, 20):
        old = base['ema'][period]
        value = close if old is None else 2 / (period + 1) * close + (1 - 2 / (period + 1)) * old
        if count >= period:
            values[f'ema{period}'] = {'time': active['time'], 'value': value}
    if count >= 50:
        values['sma50'] = {'time': active['time'], 'value': (sum(base['tail']) + close) / 50}
    return values


def daily_summary(bars, calendar, now):
    days = set(calendar.completed_days(now, 20))
    rows = [b for b in bars if datetime.fromtimestamp(b.ts, ET).date() in days]
    if not rows:
        return {'adr20': None, 'adv20': None, 'samples': 0, 'estimated': False}
    estimated = any(b.turnover is None for b in rows)
    return {'adr20': sum((b.high - b.low) / b.low for b in rows) / len(rows) * 100,
            'adv20': sum(b.turnover if b.turnover is not None else b.volume * (b.open + b.close) / 2
                         for b in rows) / len(rows),
            'samples': len(rows), 'estimated': estimated}
