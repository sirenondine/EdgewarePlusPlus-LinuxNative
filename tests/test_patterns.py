import unittest

import tests._path  # noqa: F401
from features.sextoy import PATTERN_NAMES, PATTERNS


class PatternTest(unittest.TestCase):
    def test_all_in_unit_range(self):
        for name, fn in PATTERNS.items():
            for t in (0, 0.1, 0.5, 0.9, 1.0, 1.7, 2.0, 3.3, 5.0):
                v = fn(t, 2.0)
                self.assertGreaterEqual(v, 0.0, f"{name} at {t}")
                self.assertLessEqual(v, 1.0, f"{name} at {t}")

    def test_constant(self):
        self.assertEqual(PATTERNS["constant"](0, 2.0), 1.0)
        self.assertEqual(PATTERNS["constant"](7.3, 2.0), 1.0)

    def test_pulse_square(self):
        # First half of the period on, second half off.
        self.assertEqual(PATTERNS["pulse"](0.0, 2.0), 1.0)
        self.assertEqual(PATTERNS["pulse"](0.9, 2.0), 1.0)
        self.assertEqual(PATTERNS["pulse"](1.0, 2.0), 0.0)
        self.assertEqual(PATTERNS["pulse"](1.9, 2.0), 0.0)

    def test_ramp_rises_within_period(self):
        self.assertAlmostEqual(PATTERNS["ramp"](0.0, 2.0), 0.0)
        self.assertAlmostEqual(PATTERNS["ramp"](1.0, 2.0), 0.5)
        self.assertAlmostEqual(PATTERNS["ramp"](2.0, 2.0), 0.0)  # wraps

    def test_wave_endpoints(self):
        self.assertAlmostEqual(PATTERNS["wave"](0.0, 2.0), 0.5)
        self.assertAlmostEqual(PATTERNS["wave"](0.5, 2.0), 1.0)
        self.assertAlmostEqual(PATTERNS["wave"](1.5, 2.0), 0.0)

    def test_names_match_registry(self):
        self.assertEqual(set(PATTERN_NAMES), set(PATTERNS.keys()))
        self.assertIn("constant", PATTERN_NAMES)


if __name__ == "__main__":
    unittest.main()
