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

"""Pause popups while running on battery (so Edgeware doesn't drain a laptop),
resume on AC. Reads UPower's OnBattery property on the system bus and tracks
its change signal, flipping the "battery" pause reason."""

import logging

import roll


def handle_power(settings, state) -> None:
    if not getattr(settings, "pause_on_battery", False):
        return

    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except Exception as e:
        logging.info(f"Battery pause: system bus unavailable: {e}")
        return

    def read_on_battery() -> bool | None:
        try:
            res = bus.call_sync(
                "org.freedesktop.UPower", "/org/freedesktop/UPower",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.freedesktop.UPower", "OnBattery")),
                GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 1000, None)
            return bool(res.unpack()[0])
        except Exception as e:
            logging.info(f"Battery pause: UPower query failed: {e}")
            return None

    def apply(on_battery: bool) -> None:
        if on_battery:
            logging.info("On battery — pausing popups.")
            roll.add_pause_reason("battery")
        else:
            logging.info("On AC — resuming popups.")
            roll.remove_pause_reason("battery")

    initial = read_on_battery()
    if initial is None:
        return  # no UPower; feature inert
    apply(initial)

    def on_props_changed(_c, _s, _p, _i, _sig, params) -> None:
        _iface, changed, _inv = params.unpack()
        if "OnBattery" in changed:
            apply(bool(changed["OnBattery"]))

    bus.signal_subscribe(
        "org.freedesktop.UPower", "org.freedesktop.DBus.Properties",
        "PropertiesChanged", "/org/freedesktop/UPower", None,
        Gio.DBusSignalFlags.NONE, on_props_changed)
    state._power_bus = bus  # keep the connection alive
