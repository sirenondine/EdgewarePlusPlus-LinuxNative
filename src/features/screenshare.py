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

"""Pause popups while a screencast is active, so content doesn't leak onto a
shared screen or recording.

niri reports screencasts over its event stream (CastsChanged); we watch it and
flip the "screencast" pause reason. Only niri is supported for now — on other
compositors this is a no-op (the cross-desktop path would be the
org.freedesktop.portal.ScreenCast session list, a future addition).
"""

import json
import logging
import os
import subprocess
from threading import Thread

import roll


def handle_screenshare(settings, state) -> None:
    if not getattr(settings, "pause_on_screenshare", True):
        return
    if not os.environ.get("NIRI_SOCKET"):
        logging.info("Screenshare pause: only niri is supported; skipping.")
        return

    def watch() -> None:
        try:
            proc = subprocess.Popen(
                ["niri", "msg", "--json", "event-stream"],
                stdout=subprocess.PIPE, text=True)
        except Exception as e:
            logging.info(f"Screenshare pause: could not start niri event-stream: {e}")
            return
        state._screenshare_proc = proc
        try:
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                casts = event.get("CastsChanged")
                if casts is None:
                    continue
                if casts.get("casts"):
                    logging.info("Screencast active — pausing popups.")
                    roll.add_pause_reason("screencast")
                else:
                    logging.info("Screencast ended — resuming popups.")
                    roll.remove_pause_reason("screencast")
        except Exception as e:
            logging.info(f"Screenshare watcher stopped: {e}")

    Thread(target=watch, daemon=True).start()
