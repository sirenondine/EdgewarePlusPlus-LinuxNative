# Copyright (C) 2024 Araten & Marigold
#
# This file is part of Edgeware++.
#
# Edgeware++ is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Edgeware++ is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

# Ported from upstream PR #220 by Close2real. Provides trigger_vibration() and
# continuous-vibration helpers that popups call on events (open/close/caption…).
# Pure logic — no GUI dependency. Mix into a popup class or use standalone.

import logging
import random
from typing import Any, Dict, Optional, Union


class VibrationMixin:
    def __init__(self) -> None:
        self.active_vibrations: dict[str, dict[int, bool]] = {}

    def trigger_vibration(self, event_type: str, settings: Dict[str, Any], sextoy: Any) -> None:
        """One-shot vibration for an event, per configured device."""
        try:
            if not self._check_sextoy_ready(sextoy) or not isinstance(settings, dict):
                return

            DEFAULT_CHANCE, DEFAULT_FORCE, DEFAULT_DURATION = 0, 50, 0.5

            for device_id, device_settings in settings.items():
                try:
                    device_idx = self._safe_get_device_id(device_id)
                    if device_idx is None or device_idx not in sextoy.devices:
                        continue

                    keys = {
                        "chance": f"sextoy_{event_type}_chance",
                        "force": f"sextoy_{event_type}_vibration_force",
                        "duration": f"sextoy_{event_type}_vibration_length",
                    }
                    chance = self._get_valid_value(device_settings, keys["chance"], DEFAULT_CHANCE, (int, float))
                    force_pct = self._get_valid_value(device_settings, keys["force"], DEFAULT_FORCE, (int, float))
                    duration = self._get_valid_value(device_settings, keys["duration"], DEFAULT_DURATION, (int, float))

                    if chance <= 0 or random.randint(1, 100) > chance:
                        continue

                    force = self._normalize_force(force_pct, device_settings)
                    duration = max(0.1, min(10.0, float(duration)))
                    sextoy.vibrate(device_idx, force, duration)
                except Exception as e:
                    logging.debug(f"Device {device_id} vibration error: {e}")
        except Exception as e:
            logging.debug(f"Vibration system error: {e}")

    def start_continuous_vibration(self, event_type: str, settings: Dict[str, Any], sextoy: Any) -> None:
        """Begin a held vibration for an event (e.g. while a prompt is open)."""
        try:
            if not self._check_sextoy_ready(sextoy) or not isinstance(settings, dict):
                return

            self.active_vibrations.setdefault(event_type, {})

            for device_id, device_settings in settings.items():
                try:
                    enabled_key = f"sextoy_{event_type}_enabled"
                    force_key = f"sextoy_{event_type}_vibration_force"
                    enabled = self._normalize_bool(
                        self._get_valid_value(device_settings, enabled_key, False, (bool, int, str)))
                    force_pct = self._get_valid_value(device_settings, force_key, 0, (int, float))
                    if not enabled or force_pct <= 0:
                        continue

                    device_idx = self._safe_get_device_id(device_id)
                    if device_idx is None or device_idx not in sextoy.devices:
                        continue

                    force = self._normalize_force(force_pct, device_settings)
                    sextoy.start_vibration(device_idx, force)
                    self.active_vibrations[event_type][device_idx] = True
                except Exception as e:
                    logging.debug(f"Continuous start error {event_type}/{device_id}: {e}")
        except Exception as e:
            logging.debug(f"Continuous vibration system error {event_type}: {e}")

    def stop_continuous_vibration(self, event_type: str, sextoy: Any) -> None:
        """Stop a previously started held vibration for an event."""
        try:
            if not self.active_vibrations.get(event_type):
                return
            if not self._check_sextoy_ready(sextoy, require_devices=False):
                return
            for device_idx in list(self.active_vibrations[event_type]):
                try:
                    sextoy.stop_vibration(device_idx)
                except Exception as e:
                    logging.debug(f"Error stopping continuous vib {event_type}/{device_idx}: {e}")
            self.active_vibrations.pop(event_type, None)
        except Exception as e:
            logging.debug(f"Continuous vibration stop error {event_type}: {e}")

    # ------------------------------------------------------------------
    def _check_sextoy_ready(self, sextoy: Any, require_devices: bool = True) -> bool:
        if not all(hasattr(sextoy, a) for a in ("connected", "devices", "vibrate")):
            return False
        if not sextoy.connected:
            return False
        if require_devices and not sextoy.devices:
            return False
        return True

    def _safe_get_device_id(self, device_id: Any) -> Optional[int]:
        try:
            return int(str(device_id).strip())
        except (ValueError, TypeError, AttributeError):
            return None

    def _get_valid_value(self, settings: Dict[str, Any], key: str, default: Any, valid_types: tuple) -> Any:
        try:
            value = settings.get(key, default)
            return value if isinstance(value, valid_types) else default
        except (AttributeError, TypeError):
            return default

    def _get_general_limit(self, device_settings: Dict[str, Any]) -> float:
        default = 100.0
        try:
            limit = device_settings.get("sextoy_general_vibration_force", default)
            return float(limit) if isinstance(limit, (int, float, str)) else default
        except (TypeError, ValueError):
            return default

    def _normalize_force(self, force_pct: Union[int, float], settings: Dict[str, Any]) -> float:
        normalized = max(0.0, min(1.0, float(force_pct) / 100.0))
        general = max(0.0, min(1.0, self._get_general_limit(settings) / 100.0))
        return round(general * normalized, 2)

    def _normalize_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y", "on")
        if isinstance(value, int):
            return bool(value)
        return False
