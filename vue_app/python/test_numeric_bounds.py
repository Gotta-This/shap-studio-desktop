import unittest

import bridge


class NumericBoundsTests(unittest.TestCase):
    def generate(self, **options):
        params = dict(n=70, mean=27.92, sd=14.87, digits=0, seed=12)
        params.update(options)
        return bridge.dispatch('tool.numeric', params)

    def test_omitted_and_blank_bounds_generate_positive_values(self):
        for bounds in ({}, dict(lower=None, upper=None), dict(lower=None, upper=100)):
            with self.subTest(bounds=bounds):
                result = self.generate(**bounds)
                self.assertEqual(len(result['values']), 70)
                self.assertGreaterEqual(min(result['values']), 1)
                self.assertLess(abs(result['mean'] - 27.92), .15)
                self.assertLess(abs(result['sd'] - 14.87), .2)

    def test_default_lower_bound_respects_decimal_precision(self):
        for digits in range(5):
            with self.subTest(digits=digits):
                minimum = 10 ** -digits
                result = self.generate(n=5, mean=minimum, sd=0, digits=digits)
                self.assertEqual(result['values'], [minimum] * 5)
                with self.assertRaises(ValueError):
                    self.generate(n=5, mean=0, sd=0, digits=digits)

    def test_explicit_zero_and_negative_lower_bounds_are_honored(self):
        self.assertEqual(self.generate(n=5, mean=0, sd=0, lower=0)['values'], [0] * 5)
        result = self.generate(n=20, mean=-5, sd=2, digits=2, lower=-20)
        self.assertLess(min(result['values']), 0)
        self.assertGreaterEqual(min(result['values']), -20)
        self.assertLess(abs(result['mean'] + 5), .1)
        with self.assertRaises(ValueError):
            self.generate(mean=-5)

    def test_upper_bound_is_checked_against_default_positive_lower_bound(self):
        with self.assertRaises(ValueError):
            self.generate(mean=5, sd=10, upper=10)
        with self.assertRaises(ValueError):
            self.generate(upper=0)

    def test_range_mode_still_requires_bounds_and_allows_explicit_negatives(self):
        with self.assertRaises(ValueError):
            self.generate(mode='range', lower=None, upper=10)
        result = self.generate(mode='range', lower=-10, upper=-1)
        self.assertTrue(all(-10 <= value <= -1 for value in result['values']))


if __name__ == '__main__':
    unittest.main()
