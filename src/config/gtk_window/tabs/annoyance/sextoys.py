# Copyright (C) 2025 Araten & Marigold
#
# Sex-toy support originally by Close2real (upstream PR #220).
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

import logging

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from config.vars import Vars
from features.sextoy import BUTTPLUG_AVAILABLE, PATTERN_NAMES, Sextoy

INTRO_TEXT = (
    "Drive a sex toy from Edgeware via Intiface Central. Start Intiface Central, "
    "enable its server, then connect below and scan for your toy. Each device gets "
    "its own per-event vibration settings."
)
ADDR_TEXT = "Websocket address of the running Intiface Central server."

# Per-event settings: (config key, label, kind, lo, hi). kind: pct | float | bool
_GROUPS: dict[str, list[tuple]] = {
    "General": [
        ("sextoy_general_vibration_force", "General Vibration Force (%)", "pct", 0, 100),
    ],
    "Pattern (Continuous Mode)": [
        ("sextoy_pattern", "Waveform", "combo", 0, 0),
        ("sextoy_pattern_speed", "Pattern Speed — period (sec)", "float", 0.5, 5.0),
    ],
    "Image — Continuous Mode": [
        ("sextoy_image_continuous", "Vibrate while any image popup is open", "bool", 0, 1),
        ("sextoy_image_continuous_force", "Force added per open popup (%)", "pct", 0, 100),
    ],
    "Image Open (timed)": [
        ("sextoy_image_open_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_image_open_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_image_open_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Image Close (timed)": [
        ("sextoy_image_close_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_image_close_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_image_close_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Video — Continuous Mode": [
        ("sextoy_video_continuous", "Vibrate while any video popup is open", "bool", 0, 1),
        ("sextoy_video_continuous_force", "Force added per open popup (%)", "pct", 0, 100),
    ],
    "Video Open (timed)": [
        ("sextoy_video_open_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_video_open_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_video_open_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Video Close (timed)": [
        ("sextoy_video_close_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_video_close_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_video_close_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Captions": [
        ("sextoy_caption_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_caption_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_caption_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Notifications": [
        ("sextoy_display_notification_chance", "Chance (%)", "pct", 0, 100),
        ("sextoy_display_notification_vibration_force", "Force (%)", "pct", 0, 100),
        ("sextoy_display_notification_vibration_length", "Length (sec)", "float", 0.5, 3.0),
    ],
    "Prompts": [
        ("sextoy_prompt_enabled", "Vibrate while a prompt is open", "bool", 0, 1),
        ("sextoy_prompt_vibration_force", "Force (%)", "pct", 0, 100),
    ],
}

# Sane out-of-the-box defaults: a new device vibrates on common events so the
# feature works immediately. General force is the master multiplier — 100 = no
# reduction (50 silently halves everything, which felt "broken").
_DEFAULTS: dict[str, object] = {
    "sextoy_general_vibration_force": 100,
    "sextoy_pattern": "constant", "sextoy_pattern_speed": 2.0,
    "sextoy_image_continuous": 0, "sextoy_image_continuous_force": 30,
    "sextoy_image_open_chance": 50, "sextoy_image_open_vibration_force": 60, "sextoy_image_open_vibration_length": 0.8,
    "sextoy_image_close_chance": 0, "sextoy_image_close_vibration_force": 50, "sextoy_image_close_vibration_length": 0.5,
    "sextoy_video_continuous": 0, "sextoy_video_continuous_force": 50,
    "sextoy_video_open_chance": 75, "sextoy_video_open_vibration_force": 70, "sextoy_video_open_vibration_length": 1.5,
    "sextoy_video_close_chance": 0, "sextoy_video_close_vibration_force": 50, "sextoy_video_close_vibration_length": 0.5,
    "sextoy_caption_chance": 25, "sextoy_caption_vibration_force": 50, "sextoy_caption_vibration_length": 0.5,
    "sextoy_display_notification_chance": 30, "sextoy_display_notification_vibration_force": 50, "sextoy_display_notification_vibration_length": 0.5,
    "sextoy_prompt_enabled": 1, "sextoy_prompt_vibration_force": 60,
}


def _device_defaults(name: str) -> dict:
    d = {"sextoy_name": name}
    d.update(_DEFAULTS)
    return d


class SexToysTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self._vars = vars
        # Working copy of the sextoys dict; mutated by rows and pushed back to
        # the ConfigVar so it persists on save and marks the window dirty.
        self._data: dict[str, dict] = dict(vars.sextoys.get())
        self._sextoy = Sextoy(vars)
        self._poll_source = None

        # ---- Connection --------------------------------------------------
        conn = Adw.PreferencesGroup(title="Intiface Connection", description=INTRO_TEXT)
        self.add(conn)

        if not BUTTPLUG_AVAILABLE:
            warn = Adw.ActionRow(
                title="buttplug-py not installed",
                subtitle="Run setup.sh / pip install buttplug-py to enable toy support.",
            )
            warn.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
            warn.set_sensitive(False)
            conn.add(warn)

        addr_row = Adw.EntryRow(title="Intiface Address")
        addr_row.set_text(str(vars.intiface_address.get()))
        addr_row.connect("changed", lambda r: vars.intiface_address.set(r.get_text()))
        conn.add(addr_row)

        self._conn_row = Adw.ActionRow(title="Server", subtitle="Disconnected")
        self._conn_btn = Gtk.Button(label="Connect")
        self._conn_btn.set_valign(Gtk.Align.CENTER)
        self._conn_btn.add_css_class("suggested-action")
        self._conn_btn.set_sensitive(BUTTPLUG_AVAILABLE)
        self._conn_btn.connect("clicked", self._on_toggle_connection)
        self._conn_row.add_suffix(self._conn_btn)
        conn.add(self._conn_row)

        # ---- Devices -----------------------------------------------------
        self._devices_group = Adw.PreferencesGroup(
            title="Devices",
            description="Configured and discovered toys. Connect and scan to add new ones.",
        )
        self.add(self._devices_group)

        self._device_rows: dict[str, Adw.ExpanderRow] = {}
        # (device idx, setting key) -> Gtk.Adjustment | Adw.SwitchRow, for reset.
        self._controls: dict[tuple, object] = {}
        self._empty_row = Adw.ActionRow(
            title="No devices yet",
            subtitle="Connect to Intiface and scan to discover your toy.",
        )
        self._empty_row.set_sensitive(False)
        self._devices_group.add(self._empty_row)

        # Load devices already saved in config
        for idx, settings in self._data.items():
            self._add_device_row(idx, settings.get("sextoy_name", f"Device {idx}"))

    # ------------------------------------------------------------------
    # Connection
    def _on_toggle_connection(self, _btn) -> None:
        if not self._sextoy.connected:
            self._conn_btn.set_sensitive(False)
            self._conn_row.set_subtitle("Connecting…")
            future = self._sextoy.connect()
            if future is None:
                self._conn_btn.set_sensitive(True)
                self._conn_row.set_subtitle("Could not start connection.")
                return

            def done(f):
                try:
                    f.result()
                    GLib.idle_add(self._on_connected)
                except Exception as e:
                    GLib.idle_add(lambda: self._on_connect_failed(str(e)))

            future.add_done_callback(done)
        else:
            self._sextoy.disconnect()
            if self._poll_source:
                GLib.source_remove(self._poll_source)
                self._poll_source = None
            self._conn_btn.set_label("Connect")
            self._conn_row.set_subtitle("Disconnected")

    def _on_connected(self) -> bool:
        self._conn_btn.set_label("Disconnect")
        self._conn_btn.set_sensitive(True)
        self._conn_row.set_subtitle("Connected — scanning for devices…")
        self._poll_source = GLib.timeout_add_seconds(1, self._poll_devices)
        return False

    def _on_connect_failed(self, msg: str) -> bool:
        self._conn_btn.set_label("Connect")
        self._conn_btn.set_sensitive(True)
        self._conn_row.set_subtitle(f"Connection failed: {msg}")
        return False

    def _poll_devices(self) -> bool:
        for device in self._sextoy.devices.values():
            idx = str(device.index)
            if idx not in self._data:
                name = getattr(device, "name", f"Device {idx}")
                self._data[idx] = _device_defaults(name)
                self._vars.sextoys.set(self._data)
                self._add_device_row(idx, name)
        if self._sextoy.devices:
            self._conn_row.set_subtitle(f"Connected — {len(self._sextoy.devices)} device(s)")
        return self._sextoy.connected  # keep polling while connected

    # ------------------------------------------------------------------
    # Device rows
    def _add_device_row(self, idx: str, name: str) -> None:
        if idx in self._device_rows:
            return
        self._empty_row.set_visible(False)

        expander = Adw.ExpanderRow(title=name, subtitle=f"Device {idx}")
        self._device_rows[idx] = expander

        reset_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.set_tooltip_text("Reset this device to recommended settings")
        reset_btn.connect("clicked", lambda _b, i=idx: self._reset_device(i))
        expander.add_suffix(reset_btn)

        for group_name, settings in _GROUPS.items():
            # Group header row (non-interactive divider)
            header = Adw.ActionRow(title=group_name)
            header.add_css_class("heading")
            header.set_sensitive(False)
            expander.add_row(header)
            for key, label, kind, lo, hi in settings:
                expander.add_row(self._setting_row(idx, key, label, kind, lo, hi))

        self._devices_group.add(expander)

    def _reset_device(self, idx: str) -> None:
        """Apply recommended defaults to a device's controls in place. Setting
        each widget fires its own handler, which persists into the dict."""
        for key, default in _DEFAULTS.items():
            ctrl = self._controls.get((idx, key))
            if isinstance(ctrl, Adw.SwitchRow):
                ctrl.set_active(bool(default))
            elif isinstance(ctrl, Adw.ComboRow):
                if default in PATTERN_NAMES:
                    ctrl.set_selected(PATTERN_NAMES.index(default))
            elif ctrl is not None:  # Gtk.Adjustment
                ctrl.set_value(float(default))

    def _value(self, idx: str, key: str):
        return self._data.get(idx, {}).get(key, _DEFAULTS.get(key, 0))

    def _store(self, idx: str, key: str, value) -> None:
        self._data.setdefault(idx, _device_defaults(f"Device {idx}"))[key] = value
        self._vars.sextoys.set(self._data)

    def _setting_row(self, idx: str, key: str, label: str, kind: str, lo, hi) -> Adw.PreferencesRow:
        if kind == "bool":
            row = Adw.SwitchRow(title=label)
            row.set_active(bool(self._value(idx, key)))
            row.connect("notify::active", lambda r, _p: self._store(idx, key, int(r.get_active())))
            self._controls[(idx, key)] = row
            return row

        if kind == "combo":
            row = Adw.ComboRow(title=label)
            row.set_model(Gtk.StringList.new([n.capitalize() for n in PATTERN_NAMES]))
            current = self._value(idx, key)
            if current in PATTERN_NAMES:
                row.set_selected(PATTERN_NAMES.index(current))
            row.connect("notify::selected",
                        lambda r, _p: self._store(idx, key, PATTERN_NAMES[r.get_selected()]))
            self._controls[(idx, key)] = row
            return row

        row = Adw.ActionRow(title=label)
        is_float = kind == "float"
        step = 0.1 if is_float else 1
        adj = Gtk.Adjustment(value=float(self._value(idx, key)), lower=lo, upper=hi, step_increment=step)

        def on_change(a):
            v = round(a.get_value(), 1) if is_float else int(a.get_value())
            self._store(idx, key, v)

        adj.connect("value-changed", on_change)
        self._controls[(idx, key)] = adj

        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_size_request(160, -1)
        scale.set_valign(Gtk.Align.CENTER)

        spin = Gtk.SpinButton(adjustment=adj, climb_rate=step, digits=1 if is_float else 0)
        spin.set_numeric(True)
        spin.set_valign(Gtk.Align.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(scale)
        box.append(spin)
        row.add_suffix(box)
        return row
