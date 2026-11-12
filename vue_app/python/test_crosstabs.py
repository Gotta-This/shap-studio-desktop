import unittest
from unittest.mock import patch

from crosstabs import analyze


class CrosstabsTests(unittest.TestCase):
    @patch("crosstabs._chi2_sf", return_value=0.535)
    def test_screenshot_table_matches_expected_totals_and_percentages(self, _p):
        result = analyze([[21, 50], [40, 116]], options={"fisher": False})
        self.assertEqual(result["total"], 227.0)
        self.assertEqual(result["row_totals"], [71.0, 156.0])
        self.assertEqual(result["column_totals"], [61.0, 166.0])
        self.assertEqual(result["pearson"]["df"], 1)
        self.assertAlmostEqual(result["row_percent"][0][0], 29.58, places=2)
        self.assertAlmostEqual(result["column_percent"][0][0], 34.43, places=2)
        self.assertAlmostEqual(result["expected"][0][0], 19.08, places=2)

    @patch("crosstabs._chi2_sf", return_value=0.1)
    def test_square_table_supports_kappa_and_mcnemar(self, _p):
        result = analyze([[10, 2], [1, 12]], options={"fisher": False, "kappa": True, "paired": True})
        self.assertTrue(result["kappa"]["available"])
        self.assertGreater(result["kappa"]["kappa"], 0.5)
        self.assertEqual(result["paired"]["test"], "McNemar")
        self.assertTrue(result["paired"]["continuity_corrected"])

    @patch("crosstabs._chi2_sf", return_value=0.5)
    def test_rectangular_table_uses_pairwise_column_proportions(self, _p):
        result = analyze([[8, 2, 5], [2, 8, 5]], options={"fisher": False, "pairwise": True})
        self.assertEqual(len(result["pairwise"]), 6)
        self.assertTrue(all("p_bonferroni" in item for item in result["pairwise"]))
        self.assertFalse(result["kappa"]["available"])

    def test_invalid_table_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze([[1, 2], [3]])
        with self.assertRaises(ValueError):
            analyze([[0, 0], [0, 0]])
        with self.assertRaises(ValueError):
            analyze([[0, 0], [3, 4]])


if __name__ == "__main__":
    unittest.main()
