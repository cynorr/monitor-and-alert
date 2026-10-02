"""Atomic features for one ticker's history through the evaluation date.

Inputs use lowercase column names and ascending trading-date order. No I/O,
schema repair, screening, or list membership belongs in these operators.
"""

import numpy as np
import pandas as pd


# Shared operators


def atr_distance(price, reference, atr):
    return (price - reference) / atr


def theil_sen_slope(values: np.ndarray) -> float:
    left, right = np.triu_indices(len(values), k=1)
    return float(np.median((values[right] - values[left]) / (right - left)))


def trailing_count(condition: pd.Series) -> int:
    return int(condition.iloc[::-1].cumprod().sum())


def days_since(event: pd.Series) -> int | None:
    positions = np.flatnonzero(event.to_numpy())
    return int(len(event) - 1 - positions[-1]) if len(positions) else None


def window_count(event: pd.Series, window: int) -> float:
    return event.tail(window).rolling(window).sum().iloc[-1]


# One mutually exclusive moving-average arrangement


def ma_arrangement(ema10: float, ema20: float, sma50: float) -> str:
    if pd.isna([ema10, ema20, sma50]).any():
        return "missing"
    if ema10 == ema20 or ema10 == sma50 or ema20 == sma50:
        return "others"
    if ema10 > ema20 > sma50:
        return "ema10_lead"
    if ema20 > ema10 > sma50:
        return "ema20_lead"
    if sma50 > max(ema10, ema20):
        return "under50"
    return "straddle"


# INVALIDATION


def invalidation(history: pd.DataFrame) -> dict:
    averages = history[["ema10", "ema20"]]
    extended = atr_distance(history["close"], averages.max(axis=1), history["atr20"])
    broken = atr_distance(averages.min(axis=1), history["close"], history["atr20"])
    below_days = trailing_count(history["close"] < averages.min(axis=1))
    return {
        "extended_k": extended.iloc[-1],
        "broken_k": broken.iloc[-1],
        "below_days": below_days,
    }


# GEOMETRY


def geometry(history: pd.DataFrame, window: int = 5) -> dict:
    current_close = history["close"].iloc[-1]
    columns = [
        "low",
        "high",
        "body_low",
        "body_high",
        "close",
        "ema10",
        "ema20",
        "sma50",
    ]
    slopes = (
        history[columns]
        .tail(window)
        .rolling(window)
        .apply(theil_sen_slope, raw=True)
        .iloc[-1]
    )
    return {
        f"{name}_slope_{window}d": value / current_close * 100
        for name, value in slopes.items()
    }


# TIGHTNESS


def tightness(history: pd.DataFrame, window: int = 5) -> dict:
    recent = history.tail(window)
    rolling = recent.rolling(window)
    atr = history["atr20"].iloc[-1]
    body_range = (rolling["body_high"].max() - rolling["body_low"].min()) / atr
    close_range = (rolling["close"].max() - rolling["close"].min()) / atr
    return {
        f"body_range_k_{window}d": body_range.iloc[-1],
        f"close_range_k_{window}d": close_range.iloc[-1],
        f"median_true_range_k_{window}d": (recent["tr"] / recent["atr20"])
        .rolling(window)
        .median()
        .iloc[-1],
    }


# SUPPORT / INTERACTION shared daily relationships


def ma_relationship(history: pd.DataFrame, ma: str) -> pd.DataFrame:
    close_distance = atr_distance(history["close"], history[ma], history["atr20"])
    low_distance = atr_distance(history["low"], history[ma], history["atr20"])
    below = history["close"] < history[ma]
    previous_above = history["close"].shift() >= history[ma].shift()
    previous_below = history["close"].shift() < history[ma].shift()
    return pd.DataFrame(
        {
            "close_distance": close_distance,
            "low_distance": low_distance,
            "touch": (history["low"] - history[ma]).abs()
            <= 0.5 * history["atr20"].astype("Float64"),
            "below": below,
            "downcross": previous_above & below,
            "cross": (previous_above & below) | (previous_below & ~below),
            "reclaim": (history["low"] < history[ma]) & ~below,
        }
    )


# SUPPORT


def support(relationship: pd.DataFrame, window: int = 5) -> dict:
    low_abs = relationship["low_distance"].abs()
    return {
        "close_distance_k": relationship["close_distance"].iloc[-1],
        "low_distance_k": relationship["low_distance"].iloc[-1],
        f"low_abs_distance_median_k_{window}d": low_abs.tail(window)
        .rolling(window)
        .median()
        .iloc[-1],
        f"touch_days_{window}d": window_count(relationship["touch"], window),
        f"close_below_days_{window}d": window_count(relationship["below"], window),
    }


# INTERACTION


def interaction(relationship: pd.DataFrame, window: int = 5) -> dict:
    return {
        "days_since_close_downcross": days_since(relationship["downcross"]),
        f"reclaim_count_{window}d": window_count(relationship["reclaim"], window),
        "days_since_reclaim": days_since(relationship["reclaim"]),
        # Count only the window's internal transitions, excluding its first day's incoming cross.
        f"close_cross_count_{window}d": relationship["cross"]
        .tail(window)
        .rolling(window)
        .apply(lambda values: values[1:].sum(), raw=True)
        .iloc[-1],
        f"max_penetration_k_{window}d": (-relationship["low_distance"])
        .clip(lower=0)
        .tail(window)
        .rolling(window)
        .max()
        .iloc[-1],
    }


def atomic_features(history: pd.DataFrame, window: int = 5) -> dict:
    enriched = history.assign(
        body_low=history[["open", "close"]].min(axis=1),
        body_high=history[["open", "close"]].max(axis=1),
    )
    result = {
        **invalidation(enriched),
        **geometry(enriched, window),
        **tightness(enriched, window),
        "ma_arrangement": ma_arrangement(*enriched[["ema10", "ema20", "sma50"]].iloc[-1]),
    }
    for ma in ("ema10", "ema20"):
        relationship = ma_relationship(enriched, ma)
        values = {**support(relationship, window), **interaction(relationship, window)}
        result.update({f"{ma}_{name}": value for name, value in values.items()})
    return result
