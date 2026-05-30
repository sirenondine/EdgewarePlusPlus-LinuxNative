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

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.vars import ConfigVar


# --- libadwaita preference rows (modern config tabs) -----------------------
# Adw.SwitchRow / Adw.ComboRow are final GTypes (cannot be subclassed), so these
# are factory functions that build and bind a configured row.

def AdwSwitchRow(title: str, variable: ConfigVar, subtitle: str | None = None) -> Adw.SwitchRow:
    """A switch row bound to a ConfigVar."""
    row = Adw.SwitchRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_active(bool(variable.get()))
    row.connect("notify::active", lambda r, _p: variable.set(r.get_active()))
    return row


def AdwSliderRow(title: str, variable: ConfigVar, from_: int, to: int, subtitle: str | None = None) -> Adw.ActionRow:
    """An ActionRow with an inline slider + spin button bound to a ConfigVar
    through a shared adjustment. The valid range shows as the subtitle."""
    row = Adw.ActionRow(title=title)
    row.set_subtitle(subtitle or f"{from_}–{to}")

    adj = Gtk.Adjustment(value=variable.get(), lower=from_, upper=to, step_increment=1)
    adj.connect("value-changed", lambda a: variable.set(int(a.get_value())))

    scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
    scale.set_draw_value(False)
    scale.set_digits(0)
    scale.set_hexpand(True)
    scale.set_size_request(180, -1)
    scale.set_valign(Gtk.Align.CENTER)

    spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
    spin.set_numeric(True)
    spin.set_valign(Gtk.Align.CENTER)

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_hexpand(True)
    box.append(scale)
    box.append(spin)
    row.add_suffix(box)
    return row


def AdwComboRow(title: str, variable: ConfigVar, options: dict[str, str]) -> Adw.ComboRow:
    """A ComboRow bound to a ConfigVar.

    `options` maps stored value -> description string. Keys are used as the
    dropdown labels (short); the description for the selected item is shown
    as the row subtitle so long descriptions don't overflow the combo button.
    """
    keys = list(options.keys())
    row = Adw.ComboRow(title=title)
    row.set_model(Gtk.StringList.new(keys))
    current = variable.get()
    if current in keys:
        row.set_selected(keys.index(current))
    row.set_subtitle(options.get(str(current), ""))

    def on_selected(r, _p):
        idx = r.get_selected()
        if 0 <= idx < len(keys):
            key = keys[idx]
            variable.set(key)
            r.set_subtitle(options[key])

    row.connect("notify::selected", on_selected)
    return row
