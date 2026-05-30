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

import random
from collections.abc import Callable
from dataclasses import dataclass

from config.settings import Settings

# Soft-pause. roll_targets is a no-op while paused (no new popups spawn) but the
# timer keeps running so resume is instant. Pause is reason-counted: lock,
# screencast, fullscreen and manual ("user") pauses are independent, so e.g.
# unlocking won't resume if a screencast is still active. Paused == any reason.
_pause_reasons: set[str] = set()


def add_pause_reason(reason: str) -> None:
    _pause_reasons.add(reason)


def remove_pause_reason(reason: str) -> None:
    _pause_reasons.discard(reason)


def set_paused(value: bool) -> None:
    """Manual pause/resume (the 'user' reason)."""
    if value:
        _pause_reasons.add("user")
    else:
        _pause_reasons.discard("user")


def is_paused() -> bool:
    return bool(_pause_reasons)


def toggle_paused() -> bool:
    set_paused("user" not in _pause_reasons)
    return is_paused()


@dataclass
class RollTarget:
    function: Callable[[], None]
    chance: Callable[[], int]

    def roll(self) -> None:
        if roll(self.chance()):
            self.function()


def roll_targets(settings: Settings, targets: list[RollTarget]) -> None:
    if is_paused():
        return
    if settings.single_mode:
        try:
            function = random.choices(list(map(lambda target: target.function, targets)), list(map(lambda target: target.chance(), targets)), k=1)[0]
            function()
        except ValueError:
            pass  # Do nothing if all chances are 0
    else:
        for target in targets:
            target.roll()


def roll(chance: int | float) -> bool:
    """Chance is either an integer between 0 and 100 or a float between 0 and 1"""
    return (random.randint(1, 100) if isinstance(chance, int) else random.random()) <= chance
