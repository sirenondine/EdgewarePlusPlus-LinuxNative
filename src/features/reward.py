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
import time

from gi.repository import GLib

from config.settings import Settings
from pack import Pack
from state import State

_BURST_POPUPS = 3
_BURST_INTERVAL_MS = 200
_REWARD_FORCE = 1.0
_REWARD_DURATION = 2.0
# Minimum gap between reward bursts. Several milestones can fire from a single
# event (a quest completing AND an achievement unlocking), and dismissing the
# burst can complete further quests; without this the bursts stack into a
# runaway flood. The cooldown collapses all of that into one burst.
_COOLDOWN = 20.0
_last_burst = 0.0


def reward_burst(settings: Settings, pack: Pack, state: State, popups: int = _BURST_POPUPS) -> None:
    """Celebrate a milestone: stagger a few popups and pulse any connected toy.
    No-op while paused, and rate-limited so simultaneous/cascading milestones
    cannot flood the screen."""
    global _last_burst
    import roll
    if roll.is_paused():
        return

    now = time.monotonic()
    if now - _last_burst < _COOLDOWN:
        return
    _last_burst = now

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
