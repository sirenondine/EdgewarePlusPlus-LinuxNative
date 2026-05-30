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

"""Single niri event-stream watcher driving compositor-reactive pauses:
  - screencast active        -> "screencast" pause reason (pause_on_screenshare)
  - focused app in allowlist -> "app" pause reason (pause_apps)

niri only; a no-op elsewhere. Runs one `niri msg --json event-stream`
subprocess in a daemon thread so we don't spawn one per feature.
"""

import json
import logging
import os
import subprocess
from threading import Thread

import roll


def _parse_apps(raw: str) -> set[str]:
    return {a.strip().lower() for a in raw.replace(",", " ").split() if a.strip()}


def handle_niri_watch(settings, state) -> None:
    if not os.environ.get("NIRI_SOCKET"):
        return

    want_casts = bool(getattr(settings, "pause_on_screenshare", False))
    pause_apps = _parse_apps(getattr(settings, "pause_apps", "") or "")
    companion_on = getattr(settings, "companion_enabled", False)
    # A non-zero observe interval means a timer drives screen observation instead
    # of focus changes (see handle_companion), so don't also fire it here.
    timer_observe = bool(getattr(settings, "companion_observe_interval", 0))
    want_app_react = bool(companion_on and getattr(settings, "companion_window_awareness", False))
    want_screenshot = bool(companion_on and getattr(settings, "companion_screenshot_awareness", False) and not timer_observe)
    want_companion = want_app_react or want_screenshot
    if not want_casts and not pause_apps and not want_companion:
        return  # nothing to watch

    def watch() -> None:
        try:
            proc = subprocess.Popen(
                ["niri", "msg", "--json", "event-stream"],
                stdout=subprocess.PIPE, text=True)
        except Exception as e:
            logging.info(f"niri watch: could not start event-stream: {e}")
            return
        state._niri_watch_proc = proc

        windows: dict[int, str] = {}  # window id -> app_id
        focused_id = [None]
        last_app = [None]  # for companion: react only when the focused app changes

        def eval_focus() -> None:
            app = (windows.get(focused_id[0]) or "").lower()
            if pause_apps:
                if app and app in pause_apps:
                    roll.add_pause_reason("app")
                else:
                    roll.remove_pause_reason("app")
            if want_companion and app and app != last_app[0]:
                last_app[0] = app
                # Don't narrate our own windows.
                if "edgeware" not in app and "sirenondine" not in app:
                    companion = getattr(state, "companion", None)
                    if companion:
                        if want_screenshot:
                            companion.observe()  # vision: react to the actual screen
                        else:
                            companion.react("focused_app", f"the user just switched to the app '{app}'")

        try:
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue

                if want_casts and "CastsChanged" in event:
                    if event["CastsChanged"].get("casts"):
                        roll.add_pause_reason("screencast")
                    else:
                        roll.remove_pause_reason("screencast")

                elif "WindowsChanged" in event:
                    windows.clear()
                    for w in event["WindowsChanged"].get("windows", []):
                        windows[w.get("id")] = w.get("app_id") or ""
                        if w.get("is_focused"):
                            focused_id[0] = w.get("id")
                    eval_focus()

                elif "WindowFocusChanged" in event:
                    focused_id[0] = event["WindowFocusChanged"].get("id")
                    eval_focus()
        except Exception as e:
            logging.info(f"niri watch stopped: {e}")

    Thread(target=watch, daemon=True).start()
