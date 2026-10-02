"""Build one date's cross section from daily bars, without reading or writing storage."""

import pandas as pd

from .atomic import atomic_features
from ..indicators import add_indicators, daily_metrics


def feature_row(history: pd.DataFrame, window: int = 5) -> dict:
    enriched = add_indicators(history)
    columns = ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume',
               'ema10', 'ema20', 'sma50', 'atr20']
    return {**enriched.iloc[-1][columns].to_dict(), **daily_metrics(enriched),
            **atomic_features(enriched, window)}


def build_feature_snapshot(bars: pd.DataFrame, date, window: int = 5) -> pd.DataFrame:
    """Return one row per ticker trading on date; window is at least two days."""
    history = bars.copy()
    history["date"] = pd.to_datetime(history["date"])
    date = pd.Timestamp(date)
    history = history.loc[history["date"] <= date].sort_values(["symbol", "date"])
    tickers = history.loc[history["date"] == date, "symbol"]
    history = history.loc[history["symbol"].isin(tickers)].reset_index(drop=True)

    return feature_frame([feature_row(group, window)
                          for _, group in history.groupby('symbol', sort=False)], window)


def feature_frame(rows: list[dict], window: int = 5) -> pd.DataFrame:
    result = pd.DataFrame(rows)
    count_columns = ["below_days"]
    for ma in ("ema10", "ema20"):
        count_columns.extend(
            f"{ma}_{name}"
            for name in (
                f"touch_days_{window}d",
                f"close_below_days_{window}d",
                "days_since_close_downcross",
                f"reclaim_count_{window}d",
                "days_since_reclaim",
                f"close_cross_count_{window}d",
            )
        )
    result[count_columns] = result[count_columns].astype("Int64")
    return result.reset_index(drop=True)
