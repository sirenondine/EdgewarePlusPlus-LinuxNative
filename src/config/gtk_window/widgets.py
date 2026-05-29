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
from gi.repository import Gtk

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

        if message:
            icon = Gtk.Image.new_from_icon_name("help-info-symbolic")
            icon.set_tooltip_text(message)
            title_row.append(icon)

        vbox.append(title_row)

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
        icon.set_tooltip_text(text)
        self.append(icon)


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

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        inner.set_margin_start(PAD)
        inner.set_margin_end(PAD)
        inner.set_margin_top(PAD)
        inner.set_margin_bottom(PAD)

        self._scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=Gtk.Adjustment(value=variable.get(), lower=from_, upper=to, step_increment=1),
        )
        self._scale.set_hexpand(True)
        self._scale.set_digits(0)
        self._scale.set_value_pos(Gtk.PositionType.TOP)
        self._scale.connect("value-changed", self._on_value_changed)
        inner.append(self._scale)

        manual_btn = Gtk.Button(label="Manual")
        manual_btn.connect("clicked", self._on_manual)
        inner.append(manual_btn)

        self.append(inner)

        self._label_widget = Gtk.Label(label=label, css_classes=["config-scale-label"])
        self._label_widget.set_xalign(0)
        self._label_widget.set_margin_start(PAD)
        self._label_widget.set_margin_end(PAD)
        self.append(self._label_widget)

    def _on_value_changed(self, scale: Gtk.Scale) -> None:
        self._variable.set(int(scale.get_value()))

    def _on_manual(self, _btn: Gtk.Button) -> None:
        dialog = Gtk.Dialog(title=f"Set {self._label_widget.get_text()}")
        dialog.set_default_size(300, 100)
        entry = Gtk.Entry()
        entry.set_valign(Gtk.Align.CENTER)
        entry.set_halign(Gtk.Align.CENTER)

        adj = self._scale.get_adjustment()
        entry.set_text(str(int(self._variable.get())))

        content = dialog.get_content_area()
        content.append(entry)
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Apply", Gtk.ResponseType.OK)

        entry.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))

        dialog.connect("response", lambda d, r: self._on_dialog_response(d, r, entry, adj))
        dialog.present()

    def _on_dialog_response(self, dialog: Gtk.Dialog, response: Gtk.ResponseType, entry: Gtk.Entry, adj: Gtk.Adjustment) -> None:
        if response == Gtk.ResponseType.OK:
            try:
                value = int(entry.get_text())
                value = max(int(adj.get_lower()), min(value, int(adj.get_upper())))
                self._variable.set(value)
                self._scale.set_value(value)
            except ValueError:
                pass
        dialog.destroy()

    @property
    def label_widget(self) -> Gtk.Label:
        return self._label_widget


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
        label.set_hexpand(True)
        self.append(label)

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
        enabled: bool | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        self._variable = variable
        self._items = items

        self.set_margin_start(PAD)
        self.set_margin_end(PAD)
        self.set_margin_top(PAD)
        self.set_margin_bottom(PAD)

        keys = list(items.keys())
        string_list = Gtk.StringList.new(keys)
        self._dropdown = Gtk.DropDown(model=string_list)

        current = variable.get()
        if current in keys:
            self._dropdown.set_selected(keys.index(current))

        self._dropdown.connect("notify::selected", self._on_selected)
        self.append(self._dropdown)

        self._desc = Gtk.Label(label=items.get(str(current), ""), wrap=True, css_classes=["config-dropdown-desc"])
        self._desc.set_xalign(0)
        self._desc.set_hexpand(True)
        self._desc.set_vexpand(True)
        self.append(self._desc)

    def _on_selected(self, dropdown: Gtk.DropDown, _param) -> None:
        keys = list(self._items.keys())
        selected = dropdown.get_selected()
        if 0 <= selected < len(keys):
            key = keys[selected]
            self._variable.set(key)
            self._desc.set_text(self._items[key])
