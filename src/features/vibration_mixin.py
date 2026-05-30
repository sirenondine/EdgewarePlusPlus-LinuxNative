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


# --- module-level convenience -------------------------------------------------
# A shared mixin instance for stateless one-shot triggers from popups, plus
# thin wrappers that no-op when toy support isn't active.

_shared = VibrationMixin()


def vibrate_event(event_type: str, settings: Any, sextoy: Any) -> None:
    """Fire a one-shot (timed) vibration for an event. No-op if sextoy is None."""
    if sextoy is None:
        return
    _shared.trigger_vibration(event_type, getattr(settings, "sextoys", {}) or {}, sextoy)


def start_continuous(settings: Any, sextoy: Any, token: str,
                     enabled_key: str, force_key: str) -> None:
    """Add a continuous contribution under `token` for every device where
    `enabled_key` is on and `force_key` > 0. Multiple tokens stack on a device."""
    if sextoy is None:
        return
    devices = getattr(settings, "sextoys", {}) or {}
    for dev_id, ds in devices.items():
        if not isinstance(ds, dict):
            continue
        if not _shared._normalize_bool(ds.get(enabled_key, False)):
            continue
        force_pct = _shared._get_valid_value(ds, force_key, 0, (int, float))
        if force_pct <= 0:
            continue
        idx = _shared._safe_get_device_id(dev_id)
        if idx is None or idx not in getattr(sextoy, "devices", {}):
            continue
        sextoy.add_contribution(idx, token, _shared._normalize_force(force_pct, ds))


def stop_continuous(token: str, sextoy: Any) -> None:
    """Remove a continuous contribution token from all devices."""
    if sextoy is None:
        return
    sextoy.remove_token(token)
