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

# Lightweight ambient signals for the companion's context: what media the user
# is playing system-wide (via MPRIS / playerctl). Best-effort and cached so
# building the context block stays cheap.

import logging
import shutil
import subprocess
import time

_CACHE: tuple[float, str | None] = (0.0, None)
_CACHE_TTL = 5.0  # seconds


def now_playing() -> str | None:
    """The currently playing media as "Artist - Title (status)" via playerctl,
    or None if nothing is playing / playerctl is unavailable. Cached briefly."""
    global _CACHE
    now = time.monotonic()
    if now - _CACHE[0] < _CACHE_TTL:
        return _CACHE[1]
    result = _query()
    _CACHE = (now, result)
    return result


def _query() -> str | None:
    if not shutil.which("playerctl"):
        return None
    try:
        status = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=2).stdout.strip()
        if status.lower() != "playing":
            return None
        meta = subprocess.run(
            ["playerctl", "metadata", "--format", "{{artist}} - {{title}}"],
            capture_output=True, text=True, timeout=2).stdout.strip()
        return meta or None
    except Exception as e:
        logging.debug(f"now_playing query failed: {e}")
        return None
