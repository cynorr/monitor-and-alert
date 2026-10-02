"""Pure calculations. Live previews always start from closed-bar state."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema_step(previous, close, period):
    return close if previous is None else 2 / (period + 1) * close + (1 - 2 / (period + 1)) * previous


def moving_averages(close: pd.Series, sma_period=50) -> pd.DataFrame:
    values = {10: [], 20: []}
    for value in close:
        for period, sequence in values.items():
            sequence.append(ema_step(sequence[-1] if sequence else None, value, period))
    return pd.DataFrame({'ema10': values[10], 'ema20': values[20],
                         f'sma{sma_period}': close.rolling(sma_period).mean()}, index=close.index)


def true_range(history):
    previous = history['close'].shift()
    return pd.concat([history['high'] - history['low'], (history['high'] - previous).abs(),
                      (history['low'] - previous).abs()], axis=1).max(axis=1)


def wilder_atr(tr, period=20):
    seed = tr.where(np.arange(len(tr)) >= period, tr.rolling(period).mean())
    return seed.ewm(alpha=1 / period, adjust=False).mean()


def add_indicators(history):
    result = history.copy()
    result[['ema10', 'ema20', 'sma50']] = moving_averages(result['close'])
    result['tr'] = true_range(result)
    result['atr20'] = wilder_atr(result['tr'])
    return result


def adr_adv(history):
    high, low, close, volume = (np.asarray(history[name], dtype=float)
                                for name in ('high', 'low', 'close', 'volume'))
    return {'adr20': ((high[-20:] - low[-20:]) / low[-20:] * 100).mean(),
            'adv20': (close[-20:] * volume[-20:]).mean()}


def return_from_low(history):
    low, close = (np.asarray(history[name], dtype=float) for name in ('low', 'close'))
    result = {}
    for name, window in (('rfl1m', 21), ('rfl3m', 63), ('rfl6m', 126)):
        result[name] = (close[-1] / low[-window:].min() - 1) * 100
    return result


def daily_metrics(history):
    return {**adr_adv(history), **return_from_low(history)}


def series(rows: list[dict], sma_period: int = 50) -> dict:
    result = {'ema10': [], 'ema20': [], f'sma{sma_period}': []}
    closes = [row['close'] for row in rows]
    averages = moving_averages(pd.Series(closes, dtype=float), sma_period)
    previous = {period: averages[f'ema{period}'].iloc[-1] if rows else None for period in (10,20)}
    for index, row in enumerate(rows):
        for name, period in (('ema10',10), ('ema20',20), (f'sma{sma_period}',sma_period)):
            if index + 1 >= period:
                result[name].append({'time': row['time'], 'value': float(averages[name].iloc[index])})
    return {'series': result, 'ema': previous, 'tail': closes[-(sma_period - 1):], 'count': len(closes), 'sma_period': sma_period}


def preview(base: dict, active: dict | None) -> dict:
    if active is None:
        return {}
    close, count = active['close'], base['count'] + 1
    values = {}
    for period in (10, 20):
        old = base['ema'][period]
        value = ema_step(old, close, period)
        if count >= period:
            values[f'ema{period}'] = {'time': active['time'], 'value': value}
    period = base.get('sma_period', 50)
    if count >= period:
        values[f'sma{period}'] = {'time': active['time'], 'value': (sum(base['tail']) + close) / period}
    return values


def daily_summary(bars, calendar, now):
    rows = [b for b in bars if calendar.bar_end(b.ts, '1d') <= now][-20:]
    if not rows:
        return {'adr20': None, 'adv20': None, 'samples': 0}
    metrics = adr_adv({'high': [b.high for b in rows], 'low': [b.low for b in rows],
                             'close': [b.close for b in rows], 'volume': [b.volume for b in rows]})
    return {key: metrics[key] for key in ('adr20', 'adv20')} | {'samples': len(rows)}
