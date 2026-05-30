import unittest

import tests._path  # noqa: F401  (puts src/ on the path)
from features.vibration_mixin import VibrationMixin, vibrate_event


class FakeSextoy:
    """Minimal stand-in for features.sextoy.Sextoy used by the mixin."""
    def __init__(self, connected=True, devices=None):
        self.connected = connected
        self.devices = devices if devices is not None else {0: object()}
        self.vibrations = []   # (device, force, duration)
        self.contributions = {}  # token -> (device, force)

    def vibrate(self, device_index, speed, duration=1.0):
        self.vibrations.append((device_index, speed, duration))

    def add_contribution(self, device_index, token, force):
        self.contributions[token] = (device_index, force)

    def remove_token(self, token):
        self.contributions.pop(token, None)


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.m = VibrationMixin()

    def test_force_basic(self):
        self.assertEqual(self.m._normalize_force(50, {"sextoy_general_vibration_force": 100}), 0.5)

    def test_force_general_limit_halves(self):
        self.assertEqual(self.m._normalize_force(50, {"sextoy_general_vibration_force": 50}), 0.25)

    def test_force_clamped(self):
        self.assertEqual(self.m._normalize_force(200, {"sextoy_general_vibration_force": 100}), 1.0)
        self.assertEqual(self.m._normalize_force(-10, {"sextoy_general_vibration_force": 100}), 0.0)

    def test_normalize_bool(self):
        for truthy in ("true", "1", "yes", "on", 1, True):
            self.assertTrue(self.m._normalize_bool(truthy))
        for falsy in ("no", "0", "false", 0, False, "random"):
            self.assertFalse(self.m._normalize_bool(falsy))

    def test_safe_device_id(self):
        self.assertEqual(self.m._safe_get_device_id("0"), 0)
        self.assertEqual(self.m._safe_get_device_id(" 3 "), 3)
        self.assertIsNone(self.m._safe_get_device_id("x"))
        self.assertIsNone(self.m._safe_get_device_id(None))

    def test_get_valid_value_type_filter(self):
        s = {"a": 5, "b": "str"}
        self.assertEqual(self.m._get_valid_value(s, "a", 0, (int,)), 5)
        self.assertEqual(self.m._get_valid_value(s, "b", 99, (int,)), 99)  # wrong type -> default
        self.assertEqual(self.m._get_valid_value(s, "missing", 7, (int,)), 7)


class TriggerTest(unittest.TestCase):
    def setUp(self):
        self.m = VibrationMixin()

    def test_fires_at_full_chance(self):
        toy = FakeSextoy()
        settings = {"0": {"sextoy_image_open_chance": 100,
                          "sextoy_image_open_vibration_force": 80,
                          "sextoy_image_open_vibration_length": 1.0,
                          "sextoy_general_vibration_force": 100}}
        self.m.trigger_vibration("image_open", settings, toy)
        self.assertEqual(len(toy.vibrations), 1)
        device, force, duration = toy.vibrations[0]
        self.assertEqual(device, 0)
        self.assertAlmostEqual(force, 0.8)
        self.assertEqual(duration, 1.0)

    def test_skips_at_zero_chance(self):
        toy = FakeSextoy()
        settings = {"0": {"sextoy_image_open_chance": 0}}
        self.m.trigger_vibration("image_open", settings, toy)
        self.assertEqual(toy.vibrations, [])

    def test_skips_when_disconnected(self):
        toy = FakeSextoy(connected=False)
        settings = {"0": {"sextoy_image_open_chance": 100}}
        self.m.trigger_vibration("image_open", settings, toy)
        self.assertEqual(toy.vibrations, [])

    def test_skips_unknown_device(self):
        toy = FakeSextoy(devices={})  # device "0" not present
        settings = {"0": {"sextoy_image_open_chance": 100}}
        self.m.trigger_vibration("image_open", settings, toy)
        self.assertEqual(toy.vibrations, [])

    def test_duration_clamped(self):
        toy = FakeSextoy()
        settings = {"0": {"sextoy_image_open_chance": 100,
                          "sextoy_image_open_vibration_length": 999.0}}
        self.m.trigger_vibration("image_open", settings, toy)
        self.assertLessEqual(toy.vibrations[0][2], 10.0)


class ModuleHelperTest(unittest.TestCase):
    def test_vibrate_event_none_sextoy_noop(self):
        # Must not raise when no toy is active.
        vibrate_event("image_open", object(), None)


if __name__ == "__main__":
    unittest.main()
