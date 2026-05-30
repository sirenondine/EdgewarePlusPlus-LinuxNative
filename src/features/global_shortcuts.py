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

"""Global panic hotkey via the XDG GlobalShortcuts portal
(org.freedesktop.portal.GlobalShortcuts).

The compositor owns the binding, so this needs no /dev/input access (unlike
the pynput/evdev fallback) and is the Wayland-native way to grab a global key.
"""

import logging
import secrets
from typing import Callable

from gi.repository import Gio, GLib

_PORTAL = "org.freedesktop.portal.Desktop"
_PATH = "/org/freedesktop/portal/desktop"
_IFACE = "org.freedesktop.portal.GlobalShortcuts"
_SHORTCUT_ID = "panic"


def portal_available() -> bool:
    """True if the running portal implements GlobalShortcuts."""
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        conn.call_sync(
            _PORTAL, _PATH, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (_IFACE, "version")),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 1000, None,
        )
        return True
    except Exception as e:
        logging.info(f"GlobalShortcuts portal unavailable: {e}")
        return False


class PanicShortcut:
    def __init__(self, panic_key_hint: str, on_activated: Callable[[], None], on_failed: Callable[[], None] | None = None) -> None:
        self._on_activated = on_activated
        self._on_failed = on_failed
        self._hint = _to_trigger(panic_key_hint)
        self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._sender = self._conn.get_unique_name()[1:].replace(".", "_")
        self._session_handle: str | None = None

        # Activated(session_handle, shortcut_id, timestamp, options)
        self._conn.signal_subscribe(
            _PORTAL, _IFACE, "Activated", _PATH, None,
            Gio.DBusSignalFlags.NONE, self._on_activated_signal,
        )

        self._create_session()

    def _request_token(self) -> tuple[str, str]:
        token = "edgeware_" + secrets.token_hex(8)
        path = f"{_PATH}/request/{self._sender}/{token}"
        return token, path

    def _await_response(self, request_path: str, handler: Callable[[int, GLib.Variant], None]) -> None:
        sub = {}

        def on_response(conn, sender, path, iface, signal, params):
            response, results = params.unpack()
            conn.signal_unsubscribe(sub["id"])
            handler(response, results)

        sub["id"] = self._conn.signal_subscribe(
            _PORTAL, "org.freedesktop.portal.Request", "Response", request_path, None,
            Gio.DBusSignalFlags.NONE, on_response,
        )

    def _create_session(self) -> None:
        token, request_path = self._request_token()
        session_token = "edgeware_session_" + secrets.token_hex(8)
        self._await_response(request_path, self._on_session_created)
        self._conn.call(
            _PORTAL, _PATH, _IFACE, "CreateSession",
            GLib.Variant("(a{sv})", ({
                "handle_token": GLib.Variant("s", token),
                "session_handle_token": GLib.Variant("s", session_token),
            },)),
            GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None, None,
        )

    def _on_session_created(self, response: int, results: dict) -> None:
        if response != 0:
            logging.info("GlobalShortcuts CreateSession declined.")
            self._fail()
            return
        self._session_handle = results.get("session_handle")
        self._bind()

    def _bind(self) -> None:
        token, request_path = self._request_token()

        def on_bound(r, _res):
            if r == 0:
                logging.info("Panic global shortcut bound.")
            else:
                logging.info("Panic shortcut binding declined; falling back to evdev.")
                self._fail()

        self._await_response(request_path, on_bound)

        shortcut_meta = {"description": GLib.Variant("s", "Edgeware++ Panic")}
        if self._hint:
            shortcut_meta["preferred_trigger"] = GLib.Variant("s", self._hint)

        self._conn.call(
            _PORTAL, _PATH, _IFACE, "BindShortcuts",
            GLib.Variant("(oa(sa{sv})sa{sv})", (
                self._session_handle,
                [(_SHORTCUT_ID, shortcut_meta)],
                "",  # parent_window
                {"handle_token": GLib.Variant("s", token)},
            )),
            GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None, None,
        )

    def _on_activated_signal(self, conn, sender, path, iface, signal, params) -> None:
        session_handle, shortcut_id, _timestamp, _options = params.unpack()
        if shortcut_id == _SHORTCUT_ID and session_handle == self._session_handle:
            GLib.idle_add(self._on_activated)

    def _fail(self) -> None:
        if self._on_failed:
            cb, self._on_failed = self._on_failed, None  # fire once
            GLib.idle_add(cb)


def _to_trigger(key: str) -> str:
    """Map a stored panic-key string to a portal trigger hint (best effort)."""
    if not key:
        return ""
    k = key.replace("Key.", "").strip()
    # pynput names → XDG shortcut syntax (e.g. "f9" -> "F9", "a" -> "a")
    if len(k) == 1:
        return k
    return k.upper() if k.startswith("f") and k[1:].isdigit() else k
