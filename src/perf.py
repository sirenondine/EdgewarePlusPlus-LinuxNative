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

"""Opt-in performance instrumentation. Enable with EDGEWARE_PERF=1.

- watchdog(): logs when the GLib main loop is blocked (a tick arrives late).
- timed(label): context manager logging how long a main-thread block took."""

import contextlib
import logging
import os
import time

ENABLED = os.environ.get("EDGEWARE_PERF") == "1"


def watchdog(interval: float = 0.05, stall_factor: float = 3.0) -> None:
    if not ENABLED:
        return
    from gi.repository import GLib

    state = {"last": time.monotonic()}

    def tick() -> bool:
        now = time.monotonic()
        gap = now - state["last"]
        state["last"] = now
        if gap > interval * stall_factor:
            logging.warning(f"[perf] main loop STALLED {(gap - interval) * 1000:.0f}ms")
        return True

    GLib.timeout_add(int(interval * 1000), tick)
    logging.warning("[perf] watchdog armed")


@contextlib.contextmanager
def timed(label: str):
    if not ENABLED:
        yield
        return
    t = time.monotonic()
    try:
        yield
    finally:
        ms = (time.monotonic() - t) * 1000
        if ms > 5:
            logging.warning(f"[perf] {label} {ms:.0f}ms")
