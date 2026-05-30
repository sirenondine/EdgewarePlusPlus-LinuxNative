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

"""Pause popups while the session is locked, resume on unlock.

Listens on two complementary D-Bus signals so it works across desktops:
  - org.freedesktop.login1.Session Lock/Unlock (system bus) — fires for
    loginctl lock-session, which most lockers (incl. swaylock on niri) use.
  - org.freedesktop.ScreenSaver ActiveChanged(bool) (session bus) — GNOME/KDE.

Both just flip the soft-pause flag in roll, so existing popups stay hidden
behind the locker and no new ones spawn while you're away.
"""

import logging

import roll


def handle_lock_screen(settings, state) -> None:
    if not getattr(settings, "pause_on_lock", True):
        return

    from gi.repository import Gio

    def on_lock() -> None:
        logging.info("Session locked — pausing popups.")
        roll.set_paused(True)

    def on_unlock() -> None:
        logging.info("Session unlocked — resuming popups.")
        roll.set_paused(False)

    # logind Lock/Unlock (system bus). Match any session path — only ours
    # signals on this connection in practice.
    try:
        system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        system.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Session", "Lock",
            None, None, Gio.DBusSignalFlags.NONE,
            lambda *_: on_lock())
        system.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Session", "Unlock",
            None, None, Gio.DBusSignalFlags.NONE,
            lambda *_: on_unlock())
        # Keep a reference so the connection isn't GC'd.
        state._lock_system_bus = system
        logging.info("Subscribed to logind Lock/Unlock signals.")
    except Exception as e:
        logging.info(f"logind lock signals unavailable: {e}")

    # freedesktop ScreenSaver ActiveChanged (session bus).
    try:
        session = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def on_active_changed(_c, _s, _p, _i, _sig, params) -> None:
            active = params.unpack()[0]
            (on_lock if active else on_unlock)()

        session.signal_subscribe(
            None, "org.freedesktop.ScreenSaver", "ActiveChanged",
            None, None, Gio.DBusSignalFlags.NONE, on_active_changed)
        state._lock_session_bus = session
        logging.info("Subscribed to ScreenSaver ActiveChanged signal.")
    except Exception as e:
        logging.info(f"ScreenSaver signals unavailable: {e}")
