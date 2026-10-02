import unittest

import numpy as np
import pandas as pd

from data_service.features.atomic import (
    atomic_features,
    geometry,
    interaction,
    invalidation,
    ma_arrangement,
    ma_relationship,
    support,
    theil_sen_slope,
    tightness,
)


def history(close, low=None, atr=None):
    close = np.array(close, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1 if low is None else low,
            "close": close,
            "ema10": 10.0,
            "ema20": 12.0,
            "sma50": 8.0,
            "atr20": 2.0 if atr is None else atr,
            "tr": 2.0,
        }
    )


class AtomicFeatureTest(unittest.TestCase):
    def test_invalidation_thresholds_and_signed_values(self):
        result = invalidation(history([11, 7, 7, 7]))
        self.assertEqual(result["broken_k"], 1.5)
        self.assertEqual(result["extended_k"], -2.5)
        self.assertEqual(result["below_days"], 3)
        self.assertLess(invalidation(history([15]))["broken_k"], 0)

    def test_below_streak_uses_daily_ma_and_full_history(self):
        bars = history([9] * 9)
        self.assertEqual(invalidation(bars)["below_days"], 9)
        bars.loc[8, "close"] = 10  # Equality ends the streak.
        self.assertEqual(invalidation(bars)["below_days"], 0)
        bars = history([9] * 9)
        bars.loc[5, "ema10"] = 8  # Historical MA, not today's MA.
        self.assertEqual(invalidation(bars)["below_days"], 3)

    def test_theil_sen_is_robust_to_one_outlier(self):
        self.assertEqual(theil_sen_slope(np.array([1, 2, 100, 4, 5])), 1)

    def test_all_slopes_use_current_close_and_trading_indices(self):
        bars = history([100, 102, 104, 106, 108])
        bars.index = pd.to_datetime(
            ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-08", "2026-01-09"]
        )
        names = [
            "low",
            "high",
            "body_low",
            "body_high",
            "close",
            "ema10",
            "ema20",
            "sma50",
        ]
        expected = {}
        for index, name in enumerate(names):
            slope = index - 3
            bars[name] = 100 + slope * np.arange(5)
            expected[name] = slope
        result = geometry(bars)
        for name, slope in expected.items():
            self.assertAlmostEqual(
                result[f"{name}_slope_5d"], slope / bars["close"].iloc[-1] * 100
            )

    def test_body_geometry_and_tightness_ignore_wicks(self):
        bars = history([10, 11, 12, 13, 14])
        bars["open"] = [11, 10, 13, 12, 15]
        expected_low = np.array([10, 10, 12, 12, 14])
        expected_high = np.array([11, 11, 13, 13, 15])
        bars.loc[2, "high"] = 1000
        result = atomic_features(bars)
        self.assertAlmostEqual(
            result["body_low_slope_5d"], theil_sen_slope(expected_low) / 14 * 100
        )
        self.assertAlmostEqual(
            result["body_high_slope_5d"], theil_sen_slope(expected_high) / 14 * 100
        )
        self.assertEqual(result["body_range_k_5d"], 2.5)
        self.assertEqual(result["close_range_k_5d"], 2)

    def test_true_range_median_uses_each_days_atr(self):
        bars = history([10] * 5, atr=[1, 2, 4, 8, 16])
        bars["body_low"] = 10
        bars["body_high"] = 10
        bars["tr"] = [1, 4, 12, 32, 1600]
        self.assertEqual(tightness(bars)["median_true_range_k_5d"], 3)

    def test_support_uses_signed_distances_daily_atr_and_inclusive_band(self):
        bars = history([11, 9, 10, 8, 12], low=[9, 8, 10, 7, 11], atr=[2, 4, 2, 2, 2])
        result = support(ma_relationship(bars, "ema10"))
        self.assertEqual(result["close_distance_k"], 1)
        self.assertEqual(result["low_distance_k"], 0.5)
        self.assertEqual(result["low_abs_distance_median_k_5d"], 0.5)
        self.assertEqual(result["touch_days_5d"], 4)
        self.assertEqual(result["close_below_days_5d"], 2)

    def test_touch_band_can_have_zero_width(self):
        bars = history([10] * 5, low=[10] * 5, atr=[0] * 5)
        self.assertEqual(support(ma_relationship(bars, "ema10"))["touch_days_5d"], 5)

    def test_interaction_boundary_equality_and_reclaim(self):
        bars = history([9, 10, 10, 9, 10, 9], low=[8, 9, 10, 8, 9, 8])
        result = interaction(ma_relationship(bars, "ema10"))
        self.assertEqual(
            result["close_cross_count_5d"], 3
        )  # Excludes 9 -> 10 entering window.
        self.assertEqual(result["days_since_close_downcross"], 0)
        self.assertEqual(result["reclaim_count_5d"], 2)
        self.assertEqual(result["days_since_reclaim"], 1)
        self.assertEqual(result["max_penetration_k_5d"], 1)

    def test_recent_event_can_precede_window_and_first_bar_is_not_cross(self):
        bars = history([11] + [9] * 10, low=[9] + [8] * 10)
        result = interaction(ma_relationship(bars, "ema10"))
        self.assertEqual(result["days_since_close_downcross"], 9)
        self.assertEqual(result["days_since_reclaim"], 10)
        self.assertEqual(result["reclaim_count_5d"], 0)
        self.assertEqual(result["close_cross_count_5d"], 0)
        never = interaction(ma_relationship(history([9] * 5), "ema10"))
        self.assertIsNone(never["days_since_close_downcross"])
        self.assertIsNone(never["days_since_reclaim"])

    def test_penetration_clamps_at_zero_and_reclaim_can_be_today(self):
        bars = history([11] * 5, low=[10.5] * 5)
        self.assertEqual(
            interaction(ma_relationship(bars, "ema10"))["max_penetration_k_5d"], 0
        )
        bars.loc[4, ["low", "close"]] = [9, 10]
        self.assertEqual(
            interaction(ma_relationship(bars, "ema10"))["days_since_reclaim"], 0
        )

    def test_both_ma_groups_and_configurable_window(self):
        bars = history([9, 10, 11, 12, 13])
        result = atomic_features(bars, window=3)
        self.assertEqual(
            len(result), 35
        )  # 34 numeric outputs plus one arrangement field.
        self.assertIn("low_slope_3d", result)
        self.assertNotIn("low_slope_5d", result)
        self.assertEqual(result["ema10_close_distance_k"], 1.5)
        self.assertEqual(result["ema20_close_distance_k"], 0.5)
        self.assertEqual(result["ema10_close_below_days_3d"], 0)
        self.assertEqual(result["ema20_close_below_days_3d"], 1)

    def test_ma_arrangements_are_mutually_exclusive(self):
        cases = [
            ((12, 11, 10), "ema10_lead"),
            ((11, 12, 10), "ema20_lead"),
            ((9, 8, 10), "under50"),
            ((8, 9, 10), "under50"),
            ((11, 9, 10), "straddle"),
            ((9, 11, 10), "straddle"),
            ((11, 11, 10), "others"),
            ((9, 9, 10), "others"),
            ((11, 10, 10), "others"),
            ((10, 10, 10), "others"),
            ((12, 11, np.nan), "missing"),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertEqual(ma_arrangement(*values), expected)
