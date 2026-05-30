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

# Local, opt-in gamification: XP and levels earned from popup interactions.
# Fully local (a plain JSON state file), no leaderboard, no telemetry. This
# module is GUI-agnostic: callers fire record(event); the UI hook (level-up
# notification) is injected via set_level_up_callback. Achievements and quests
# build on this in later steps.

import json
import logging
import os
import tempfile
import time

from paths import Data

# XP awarded per event. Counters are tracked for every event regardless of XP.
EVENT_XP = {
    "popup_closed": 1,
    "prompt_completed": 5,
    "denial_seen": 2,
    "playtime_minute": 1,
}

LEVEL_STEP = 25  # tuning constant for the level curve
_SAVE_THROTTLE = 3.0  # seconds; coalesce frequent writes during popup floods


def cumulative_xp(level: int) -> int:
    """Total XP required to be AT `level` (level 0 = 0 XP)."""
    return LEVEL_STEP * level * (level + 1) // 2


def level_for_xp(xp: int) -> int:
    level = 0
    while cumulative_xp(level + 1) <= xp:
        level += 1
    return level


class Progress:
    def __init__(self) -> None:
        self.xp = 0
        self.level = 0
        self.counters: dict[str, int] = {}
        self.achievements: set[str] = set()
        self.on_level_up = None  # callback(new_level) injected by the UI layer
        self._last_save = 0.0
        self._dirty = False

    # ------------------------------------------------------------------
    def record(self, event: str, count: int = 1, xp: int | None = None) -> None:
        """Log `count` occurrences of `event`, award XP, persist (throttled)."""
        self.counters[event] = self.counters.get(event, 0) + count
        gain = (EVENT_XP.get(event, 0) if xp is None else xp) * count
        if gain > 0:
            self._add_xp(gain)
        self._dirty = True
        self._maybe_save()

    def _add_xp(self, gain: int) -> None:
        self.xp += gain
        new_level = level_for_xp(self.xp)
        if new_level > self.level:
            self.level = new_level
            if self.on_level_up:
                try:
                    self.on_level_up(new_level)
                except Exception as e:
                    logging.warning(f"gamification level-up callback error: {e}")

    def xp_into_level(self) -> tuple[int, int]:
        """(xp earned into the current level, xp the current level spans) — for a
        progress bar."""
        base = cumulative_xp(self.level)
        span = cumulative_xp(self.level + 1) - base
        return self.xp - base, span

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "xp": self.xp,
            "level": self.level,
            "counters": self.counters,
            "achievements": sorted(self.achievements),
        }

    def load(self) -> None:
        try:
            data = json.loads(Data.PROGRESS.read_text(encoding="utf-8"))
            self.xp = int(data.get("xp", 0))
            self.counters = {str(k): int(v) for k, v in (data.get("counters") or {}).items()}
            self.achievements = set(data.get("achievements") or [])
            # Trust persisted level but never let it disagree with the curve.
            self.level = max(int(data.get("level", 0)), level_for_xp(self.xp))
            logging.info(f"Gamification: loaded level {self.level}, {self.xp} XP.")
        except FileNotFoundError:
            logging.info("Gamification: no progress file yet, starting fresh.")
        except Exception as e:
            logging.warning(f"Gamification: failed to load progress ({e}); starting fresh.")

    def _maybe_save(self) -> None:
        now = time.monotonic()
        if now - self._last_save >= _SAVE_THROTTLE:
            self.save()

    def save(self) -> None:
        """Atomically write progress (temp file + rename)."""
        if not self._dirty:
            return
        try:
            Data.PROGRESS.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=Data.PROGRESS.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp, Data.PROGRESS)
            self._last_save = time.monotonic()
            self._dirty = False
        except Exception as e:
            logging.warning(f"Gamification: failed to save progress: {e}")


# --- module-level singleton ---------------------------------------------------
_progress: Progress | None = None


def progress() -> Progress:
    global _progress
    if _progress is None:
        _progress = Progress()
        _progress.load()
    return _progress


def record(event: str, count: int = 1, xp: int | None = None) -> None:
    progress().record(event, count, xp)


def set_level_up_callback(callback) -> None:
    progress().on_level_up = callback


def flush() -> None:
    """Force a save (e.g. before exit)."""
    if _progress is not None:
        _progress.save()
