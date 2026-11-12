import unittest
from unittest.mock import patch

from means_ttest import analyze


class MeansTTestTests(unittest.TestCase):
    @patch("means_ttest._t_sf", return_value=0.000001)
    @patch("means_ttest._t_ppf", return_value=1.9706)
    def test_screenshot_values_match_pooled_t_test(self, _ppf, _sf):
        result = analyze(
            {"mean": 12.47, "sd": 2.37, "n": 71},
            {"mean": 11.00, "sd": 1.92, "n": 156},
        )
        self.assertAlmostEqual(result["difference"], -1.47, places=2)
        self.assertAlmostEqual(result["pooled_sd"], 2.071, places=3)
        self.assertAlmostEqual(result["standard_error"], 0.296, places=3)
        self.assertAlmostEqual(result["t"], -4.959, places=3)
        self.assertEqual(result["df"], 225)
        self.assertAlmostEqual(result["ci"]["low"], -2.054, places=3)
        self.assertAlmostEqual(result["ci"]["high"], -0.886, places=3)

    @patch("means_ttest._t_sf", return_value=0.2)
    @patch("means_ttest._t_ppf", return_value=2.0)
    def test_welch_variant_has_fractional_df_and_no_pooled_sd(self, _ppf, _sf):
        result = analyze(
            {"mean": 10, "sd": 1, "n": 10},
            {"mean": 8, "sd": 4, "n": 12},
            method="welch",
        )
        self.assertEqual(result["method"], "welch")
        self.assertIsNone(result["pooled_sd"])
        self.assertNotEqual(result["df"], 20)

    def test_invalid_summary_statistics_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze({"mean": 1, "sd": -1, "n": 10}, {"mean": 1, "sd": 1, "n": 10})
        with self.assertRaises(ValueError):
            analyze({"mean": 1, "sd": 1, "n": 1}, {"mean": 1, "sd": 1, "n": 10})


if __name__ == "__main__":
    unittest.main()
