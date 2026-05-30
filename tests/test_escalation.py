import unittest

import tests._path  # noqa: F401
from features import escalation


class EscalationTest(unittest.TestCase):
    def setUp(self):
        escalation.reset()

    def test_base_delay_when_idle(self):
        self.assertEqual(escalation.effective_delay(10000), 10000)
        self.assertAlmostEqual(escalation.level(), 0.0, places=3)

    def test_interaction_raises_level_and_shortens_delay(self):
        before = escalation.effective_delay(10000)
        for _ in range(5):
            escalation.record_interaction()
        after = escalation.effective_delay(10000)
        self.assertLess(after, before)
        self.assertGreater(escalation.level(), 0.0)

    def test_level_capped_at_one(self):
        for _ in range(50):
            escalation.record_interaction()
        self.assertLessEqual(escalation.level(), 1.0)
        # At max engagement the delay should hit the floor (~30% of base).
        self.assertLessEqual(escalation.effective_delay(10000), 3100)

    def test_delay_never_zero(self):
        for _ in range(50):
            escalation.record_interaction()
        self.assertGreaterEqual(escalation.effective_delay(1), 1)


if __name__ == "__main__":
    unittest.main()
