import unittest

import tests._path  # noqa: F401
import roll


class FakeSettings:
    single_mode = False


class PauseReasonTest(unittest.TestCase):
    def setUp(self):
        # Reset global state between tests.
        roll._pause_reasons.clear()

    def test_default_not_paused(self):
        self.assertFalse(roll.is_paused())

    def test_reasons_independent(self):
        roll.add_pause_reason("lock")
        self.assertTrue(roll.is_paused())
        roll.add_pause_reason("screencast")
        roll.remove_pause_reason("lock")
        self.assertTrue(roll.is_paused())  # screencast still holds
        roll.remove_pause_reason("screencast")
        self.assertFalse(roll.is_paused())

    def test_manual_set_and_toggle(self):
        roll.set_paused(True)
        self.assertTrue(roll.is_paused())
        roll.set_paused(False)
        self.assertFalse(roll.is_paused())
        self.assertTrue(roll.toggle_paused())
        self.assertFalse(roll.toggle_paused())

    def test_manual_independent_of_reasons(self):
        roll.add_pause_reason("lock")
        roll.set_paused(False)   # clears only "user"
        self.assertTrue(roll.is_paused())  # lock remains


class RollTargetsTest(unittest.TestCase):
    def setUp(self):
        roll._pause_reasons.clear()

    def test_paused_skips_targets(self):
        fired = []
        targets = [roll.RollTarget(lambda: fired.append(1), lambda: 100)]
        roll.set_paused(True)
        roll.roll_targets(FakeSettings(), targets)
        self.assertEqual(fired, [])
        roll.set_paused(False)
        roll.roll_targets(FakeSettings(), targets)
        self.assertEqual(fired, [1])


if __name__ == "__main__":
    unittest.main()
