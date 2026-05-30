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

"""Engagement escalation: the more the user interacts (closes popups), the
faster popups spawn; it decays back to normal when they stop. A user-activity
proxy that needs no idle protocol — closing popups means engaged, silence
means idle, so the spawn rate tracks attention.

State is a single 0..1 "level" that rises on each interaction and decays
exponentially with a half-life. The level scales the popup delay between the
base value (level 0) and MIN_FACTOR * base (level 1)."""

import time

_HALF_LIFE = 30.0   # seconds for the level to halve with no interaction
_STEP = 0.15        # level added per popup interaction
_MIN_FACTOR = 0.3   # at full engagement, delay is 30% of base (~3x faster)

_level = 0.0
_last = time.monotonic()


def _decay() -> None:
    global _level, _last
    now = time.monotonic()
    elapsed = now - _last
    if elapsed > 0:
        _level *= 0.5 ** (elapsed / _HALF_LIFE)
        _last = now


def record_interaction() -> None:
    """Call when the user closes/dismisses a popup."""
    global _level
    _decay()
    _level = min(1.0, _level + _STEP)


def level() -> float:
    _decay()
    return _level


def effective_delay(base_delay: int) -> int:
    """Scale the popup delay down as engagement rises."""
    factor = 1.0 - level() * (1.0 - _MIN_FACTOR)
    return max(1, int(base_delay * factor))


def reset() -> None:
    global _level, _last
    _level = 0.0
    _last = time.monotonic()
