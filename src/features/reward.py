# Copyright (C) 2025 Araten & Marigold
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

# A short celebratory "reward" fired when a gamification milestone (achievement
# or quest) is reached: a quick burst of popups and a strong toy buzz. Suppressed
# while paused. Spawning is staggered on the main loop so it doesn't hitch.

import logging

from gi.repository import GLib

from config.settings import Settings
from pack import Pack
from state import State

_BURST_POPUPS = 5
_BURST_INTERVAL_MS = 150
_REWARD_FORCE = 1.0
_REWARD_DURATION = 2.0


def reward_burst(settings: Settings, pack: Pack, state: State, popups: int = _BURST_POPUPS) -> None:
    """Celebrate a milestone: stagger a few popups and pulse any connected toy.
    No-op while paused."""
    import roll
    if roll.is_paused():
        return

    from features.image_popup import ImagePopup

    def spawn(remaining: int) -> bool:
        if remaining <= 0:
            return False
        try:
            ImagePopup(settings, pack, state)
        except Exception as e:
            logging.debug(f"reward popup spawn failed: {e}")
        GLib.timeout_add(_BURST_INTERVAL_MS, lambda: spawn(remaining - 1))
        return False

    GLib.idle_add(lambda: spawn(popups))

    toy = state.sextoy
    if toy and getattr(toy, "connected", False):
        try:
            for idx in list(getattr(toy, "devices", {}) or {}):
                toy.vibrate(idx, _REWARD_FORCE, _REWARD_DURATION)
        except Exception as e:
            logging.debug(f"reward vibration failed: {e}")
