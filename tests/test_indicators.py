import unittest

import numpy as np
import pandas as pd

from data_service.indicators import moving_averages, true_range, wilder_atr


class IndicatorTest(unittest.TestCase):
    def test_true_range_includes_gaps_and_initial_intraday_range(self):
        bars = pd.DataFrame(
            {"high": [11, 15, 9], "low": [9, 14, 7], "close": [10, 14.5, 8]}
        )
        np.testing.assert_allclose(true_range(bars), [2, 5, 7.5])

    def test_wilder_seed_and_recurrence(self):
        tr = pd.Series(list(range(1, 21)) + [30, 5], dtype=float)
        atr = wilder_atr(tr)
        self.assertTrue(atr.iloc[:19].isna().all())
        self.assertEqual(atr.iloc[19], 10.5)
        self.assertAlmostEqual(atr.iloc[20], (10.5 * 19 + 30) / 20)
        self.assertAlmostEqual(atr.iloc[21], (atr.iloc[20] * 19 + 5) / 20)
        self.assertTrue(wilder_atr(tr.iloc[:10]).isna().all())

    def test_moving_average_initialization_and_sma_window(self):
        close = pd.Series([10.0] * 49 + [20.0])
        ma = moving_averages(close)
        self.assertEqual(ma["ema10"].iloc[0], 10)
        self.assertAlmostEqual(ma["ema10"].iloc[-1], 10 + 10 * 2 / 11)
        self.assertAlmostEqual(ma["ema20"].iloc[-1], 10 + 10 * 2 / 21)
        self.assertTrue(ma["sma50"].iloc[:49].isna().all())
        self.assertEqual(ma["sma50"].iloc[-1], 10.2)
