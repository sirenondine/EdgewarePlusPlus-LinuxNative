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

require_version("Gdk", "4.0")
require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from config.vars import ConfigVar

PAD = 4


class ConfigSection(Gtk.Frame):
    def __init__(self, title: str, message: str | None = None) -> None:
        super().__init__(css_classes=["config-section"])
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        vbox.set_margin_start(PAD)
        vbox.set_margin_end(PAD)
        vbox.set_margin_top(PAD)
        vbox.set_margin_bottom(PAD)
        self.set_child(vbox)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        title_label = Gtk.Label(label=title, css_classes=["config-section-title"], wrap=True)
        title_label.set_xalign(0)
        title_label.set_hexpand(True)
        title_row.append(title_label)

        vbox.append(title_row)

        if message:
            msg_lbl = Gtk.Label(label=message, wrap=True)
            msg_lbl.set_xalign(0)
            msg_lbl.add_css_class("dim-label")
            vbox.append(msg_lbl)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.append(self._content)

    @property
    def content(self) -> Gtk.Box:
        return self._content

    def append(self, widget: Gtk.Widget) -> None:
        self._content.append(widget)


class ConfigMessage(Gtk.Box):
    def __init__(self, text: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        icon = Gtk.Image.new_from_icon_name("help-info-symbolic")
        self.append(icon)
        lbl = Gtk.Label(label=text, wrap=True)
        lbl.set_xalign(0)
        lbl.add_css_class("dim-label")
        self.append(lbl)


class ConfigRow(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)


class ConfigTitle(Gtk.Label):
    def __init__(self, text: str) -> None:
        super().__init__(label=text, css_classes=["config-title"])
        self.set_xalign(0)


class ConfigScale(Gtk.Box):
    def __init__(
        self,
        label: str,
        variable: ConfigVar,
        from_: int,
        to: int,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._variable = variable
        self._enabled = enabled

        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label_row.set_margin_start(PAD)
        label_row.set_margin_end(PAD)

        self._label_widget = Gtk.Label(label=label, css_classes=["config-scale-label"])
        self._label_widget.set_xalign(0)
        self._label_widget.set_hexpand(True)
        label_row.append(self._label_widget)

        range_lbl = Gtk.Label(label=f"({from_}–{to})")
        range_lbl.add_css_class("dim-label")
        label_row.append(range_lbl)

        self.append(label_row)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        inner.set_margin_start(PAD)
        inner.set_margin_end(PAD)
        inner.set_margin_top(PAD)
        inner.set_margin_bottom(PAD)

        adj = Gtk.Adjustment(value=variable.get(), lower=from_, upper=to, step_increment=1)
        adj.connect("value-changed", self._on_adj_changed)

        self._scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        self._scale.set_hexpand(True)
        self._scale.set_digits(0)
        self._scale.set_draw_value(False)
        inner.append(self._scale)

        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        spin.set_numeric(True)
        spin.set_valign(Gtk.Align.CENTER)
        inner.append(spin)

        self.append(inner)

    def _on_adj_changed(self, adj: Gtk.Adjustment) -> None:
        self._variable.set(int(adj.get_value()))



class ConfigToggle(Gtk.Box):
    def __init__(
        self,
        text: str,
        variable: ConfigVar,
        enabled: bool | None = None,
        tooltip: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        self._variable = variable
        self._enabled = enabled
        self.set_hexpand(False)
        self.set_valign(Gtk.Align.CENTER)

        self.set_margin_start(PAD)
        self.set_margin_end(PAD)
        self.set_margin_top(PAD)
        self.set_margin_bottom(PAD)
        self.add_css_class("config-toggle")

        self._switch = Gtk.Switch()
        self._switch.set_active(bool(variable.get()))
        self._switch.connect("notify::active", self._on_toggled)
        self.append(self._switch)

        label = Gtk.Label(label=text, css_classes=["config-toggle-label"])
        label.set_xalign(0)
        label.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        self.append(label)

        gesture = Gtk.GestureClick.new()
        gesture.connect("released", lambda _g, _n, _x, _y: self._switch.set_active(not self._switch.get_active()))
        label.add_controller(gesture)

        if tooltip:
            self.set_tooltip_text(tooltip)

    def _on_toggled(self, switch: Gtk.Switch, _param) -> None:
        self._variable.set(switch.get_active())

    def set_active(self, active: bool) -> None:
        self._switch.set_active(active)
        self._variable.set(active)


class ConfigDropdown(Gtk.Box):
    def __init__(
        self,
        variable: ConfigVar,
        items: dict[str, str],
        label: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL if label else Gtk.Orientation.HORIZONTAL, spacing=PAD)
        self._variable = variable
        self._items = items

        self.set_margin_start(PAD)
        self.set_margin_end(PAD)
        self.set_margin_top(PAD)
        self.set_margin_bottom(PAD)
        self.set_valign(Gtk.Align.CENTER)

        if label:
            lbl = Gtk.Label(label=label)
            lbl.set_xalign(0)
            self.append(lbl)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        self.append(inner)

        keys = list(items.keys())
        string_list = Gtk.StringList.new(keys)
        self._dropdown = Gtk.DropDown(model=string_list)

        current = variable.get()
        if current in keys:
            self._dropdown.set_selected(keys.index(current))

        self._dropdown.connect("notify::selected", self._on_selected)
        inner.append(self._dropdown)

        self._desc = Gtk.Label(label=items.get(str(current), ""), wrap=True, css_classes=["config-dropdown-desc"])
        self._desc.set_xalign(0)
        self._desc.set_hexpand(True)
        inner.append(self._desc)

    def _on_selected(self, dropdown: Gtk.DropDown, _param) -> None:
        keys = list(self._items.keys())
        selected = dropdown.get_selected()
        if 0 <= selected < len(keys):
            key = keys[selected]
            self._variable.set(key)
            self._desc.set_text(self._items[key])
