import unittest

import numpy as np
import pandas as pd

from data_service.features.snapshot import build_feature_snapshot


def bars_for(ticker, scale=1):
    dates = pd.bdate_range("2025-01-01", periods=150)
    close = (100 + np.arange(150) * 0.5) * scale
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ticker,
            "open": close - scale,
            "high": close + 2 * scale,
            "low": close - 2 * scale,
            "close": close,
            "volume": 1000000,
        }
    )


class FeatureSnapshotTest(unittest.TestCase):
    def test_cutoff_independence_scale_invariance_and_input_unchanged(self):
        first = bars_for("AAA")
        second = bars_for("BBB", 10)
        date = first["date"].iloc[-2]
        stale = bars_for("STALE").iloc[:-2]
        bars = pd.concat([first, second, stale]).sample(frac=1, random_state=1)
        original = bars.copy(deep=True)
        result = build_feature_snapshot(bars, date).set_index("symbol")
        pd.testing.assert_frame_equal(bars, original)
        self.assertEqual(set(result.index), {"AAA", "BBB"})
        self.assertEqual(result["date"].unique().tolist(), [date])
        pd.testing.assert_frame_equal(
            result,
            build_feature_snapshot(bars[bars["date"] <= date], date).set_index(
                "symbol"
            ),
        )
        for name in [
            "low_slope_5d",
            "body_range_k_5d",
            "extended_k",
            "ema20_low_distance_k",
        ]:
            self.assertAlmostEqual(result.loc["AAA", name], result.loc["BBB", name])
        self.assertEqual(str(result["below_days"].dtype), "Int64")
        self.assertEqual(str(result["ema10_days_since_close_downcross"].dtype), "Int64")
        self.assertTrue(result["ema10_days_since_close_downcross"].isna().all())
        self.assertEqual(len(result.columns) + 1, 51)

    def test_existing_continuous_metrics_and_single_custom_window(self):
        bars = bars_for("AAA")
        result = build_feature_snapshot(bars, bars["date"].iloc[-1], window=3).iloc[0]
        self.assertAlmostEqual(
            result["adr20"],
            ((bars["high"] - bars["low"]) / bars["low"] * 100).tail(20).mean(),
        )
        self.assertAlmostEqual(
            result["adv20"], (bars["close"] * bars["volume"]).tail(20).mean()
        )
        for name, window in [("rfl1m", 21), ("rfl3m", 63), ("rfl6m", 126)]:
            self.assertAlmostEqual(
                result[name],
                (bars["close"].iloc[-1] / bars["low"].tail(window).min() - 1) * 100,
            )
        self.assertIn("ema20_reclaim_count_3d", result.index)
        self.assertFalse(any(name.endswith("_5d") for name in result.index))

    def test_indicator_warmup_retains_natural_nulls(self):
        bars = bars_for("NEW").head(1)
        result = build_feature_snapshot(bars, bars["date"].iloc[-1]).iloc[0]
        for name in [
            "atr20",
            "sma50",
            "low_slope_5d",
            "ema10_touch_days_5d",
            "ema10_close_cross_count_5d",
        ]:
            self.assertTrue(pd.isna(result[name]), name)
        self.assertEqual(result["ma_arrangement"], "missing")
