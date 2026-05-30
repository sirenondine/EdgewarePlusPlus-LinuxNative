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

import getpass
import logging
import os
import random
import sys
import time
from hashlib import md5

from config.settings import Settings
from paths import Data, PackPaths
from screeninfo import Monitor, get_monitors


class RedactUsernameFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return message.replace(getpass.getuser(), "[USERNAME_REDACTED]")


def init_logging(filename: str) -> str:
    Data.LOGS.mkdir(parents=True, exist_ok=True)
    log_time = time.asctime().replace(" ", "_").replace(":", "-")
    log_file = f"{log_time}-{filename}.txt"

    handlers = [logging.StreamHandler(stream=sys.stdout), logging.FileHandler(filename=Data.LOGS / log_file)]
    for handler in handlers:
        handler.setFormatter(RedactUsernameFormatter("%(levelname)s:%(message)s"))

    logging.basicConfig(level=logging.INFO, force=True, handlers=handlers)

    logging.info(f"Python version: {sys.version}")
    return log_file


def compute_mood_id(paths: PackPaths) -> str:
    data = []
    for path, dirs, files in os.walk(paths.root):
        data.append(sorted(files))

    return md5(str(sorted(data)).encode()).hexdigest()


def primary_monitor() -> Monitor | None:
    monitors = get_monitors()

    # Return the first monitor if no primary monitor is found
    return next((m for m in monitors if m.is_primary), monitors[0] if monitors else None)


def gdk_monitor_for(monitor) -> object | None:
    """Map a screeninfo Monitor to the matching Gdk.Monitor by geometry origin."""
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    if not display:
        return None
    monitors = display.get_monitors()
    best = None
    for i in range(monitors.get_n_items()):
        gdk_mon = monitors.get_item(i)
        geo = gdk_mon.get_geometry()
        if geo.x == monitor.x and geo.y == monitor.y:
            return gdk_mon
        if best is None:
            best = gdk_mon
    return best


def after(delay_ms: int, callback) -> int:
    """One-shot GLib timer — equivalent to Tkinter root.after(). Returns source ID."""
    from gi.repository import GLib
    def _run():
        callback()
        return GLib.SOURCE_REMOVE
    return GLib.timeout_add(delay_ms, _run)


def after_cancel(source_id: int | None) -> None:
    """Cancel a GLib timer by source ID."""
    from gi.repository import GLib
    if source_id is not None:
        try:
            GLib.source_remove(source_id)
        except Exception:
            pass


def focused_monitor() -> Monitor | None:
    """The screeninfo Monitor for the compositor's currently focused output.
    niri only (uses its IPC); None elsewhere or on any error."""
    import os
    if not os.environ.get("NIRI_SOCKET"):
        return None
    try:
        import json
        import subprocess
        out = subprocess.run(
            ["niri", "msg", "--json", "focused-output"],
            capture_output=True, text=True, timeout=1)
        name = json.loads(out.stdout).get("name")
        if name:
            return next((m for m in get_monitors() if m.name == name), None)
    except Exception:
        pass
    return None


_monitor_cache: tuple[float, list[Monitor]] | None = None
_MONITOR_TTL = 2.0  # seconds; long enough to coalesce popup bursts, short enough to notice hotplug


def cached_monitors() -> list[Monitor]:
    """get_monitors() (~5-8ms each) cached briefly so a burst of popups doesn't
    re-query the display once per popup."""
    global _monitor_cache
    now = time.monotonic()
    if _monitor_cache and now - _monitor_cache[0] < _MONITOR_TTL:
        return _monitor_cache[1]
    monitors = get_monitors()
    _monitor_cache = (now, monitors)
    return monitors


def random_monitor(settings: Settings) -> Monitor:
    _all = cached_monitors()
    enabled_monitors = [m for m in _all if m.name not in settings.disabled_monitors]

    if getattr(settings, "spawn_on_active_monitor", False):
        focused = focused_monitor()
        if focused and focused.name not in settings.disabled_monitors:
            return focused

    return random.choice(enabled_monitors or get_monitors())
