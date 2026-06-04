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

from collections.abc import Callable

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.vars import ConfigVar


# --- libadwaita preference rows (modern config tabs) -----------------------
# Adw.SwitchRow / Adw.ComboRow are final GTypes (cannot be subclassed), so these
# are factory functions that build and bind a configured row.


def _string_list_setup(_factory, item) -> None:
    lbl = Gtk.Label(xalign=0, wrap=True)
    lbl.set_margin_start(8)
    lbl.set_margin_top(4)
    lbl.set_margin_bottom(4)
    item.set_child(lbl)


def _string_list_bind(_factory, item) -> None:
    item.get_child().set_text(item.get_item().get_string())


def make_string_list_group(
    title: str,
    description: str,
    initial: list[str],
    on_change: Callable[[list[str]], None],
    *,
    add_prompt: str = "Item (or space-separated items)",
    reset_to: list[str] | None = None,
    header_extra: "list[Gtk.Widget] | None" = None,
    appender_out: "list | None" = None,
) -> Adw.PreferencesGroup:
    """An add / remove / (optional) reset editor for an ordered list of strings,
    rendered as a scrollable card with +/-/undo buttons in the group header.

    `initial` seeds the list; `on_change` is called with the full current list
    after every edit (the caller persists). If `reset_to` is given, a reset
    button restores the list to it; otherwise no reset button is shown.
    """
    from config.gtk_window.toast import name_popover

    group = Adw.PreferencesGroup(title=title, description=description)
    store = Gtk.StringList.new(list(initial))
    selection = Gtk.SingleSelection.new(store)

    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", _string_list_setup)
    factory.connect("bind", _string_list_bind)
    listview = Gtk.ListView.new(selection, factory)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_min_content_height(140)
    scroller.set_child(listview)
    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_child(scroller)
    group.add(frame)

    def sync() -> None:
        on_change([store.get_string(i) for i in range(store.get_n_items())])

    def add(text: str) -> None:
        for item in text.split():
            store.append(item)
        sync()

    remove_btn = Gtk.Button(icon_name="list-remove-symbolic")
    remove_btn.set_tooltip_text("Remove selected")
    # SingleSelection auto-selects row 0, but notify::selected won't fire for
    # that initial pick, so seed sensitivity from the current selection.
    remove_btn.set_sensitive(selection.get_selected() != Gtk.INVALID_LIST_POSITION)
    selection.connect("notify::selected", lambda sel, _p: remove_btn.set_sensitive(
        sel.get_selected() != Gtk.INVALID_LIST_POSITION))

    def on_remove(_b) -> None:
        pos = selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION:
            store.remove(pos)
            sync()

    remove_btn.connect("clicked", on_remove)

    add_btn = Gtk.Button(icon_name="list-add-symbolic")
    add_btn.set_tooltip_text("Add")
    add_btn.connect("clicked", lambda b: name_popover(b, add_prompt, add))

    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    buttons.append(add_btn)
    buttons.append(remove_btn)

    if reset_to is not None:
        def on_reset(_b) -> None:
            while store.get_n_items() > 0:
                store.remove(0)
            for item in reset_to:
                store.append(item)
            sync()
        reset_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        reset_btn.set_tooltip_text("Reset")
        reset_btn.connect("clicked", on_reset)
        buttons.append(reset_btn)

    if header_extra:
        for w in header_extra:
            buttons.append(w)

    group.set_header_suffix(buttons)

    # Expose a function that bulk-appends items and syncs the store. Used by the
    # AI generate dialog to update the UI after generation without rebuilding.
    if appender_out is not None:
        def _bulk_append(items: list[str]) -> None:
            for item in items:
                s = item.strip()
                if s:
                    store.append(s)
            sync()
        appender_out.append(_bulk_append)

    return group


def bind_visibility(widget: Gtk.Widget, variable: ConfigVar, predicate) -> None:
    """Show `widget` only while predicate(variable value) is true. Updates live
    as the controlling ConfigVar changes (and applies the initial state now)."""
    def _update(value: object) -> None:
        widget.set_visible(bool(predicate(value)))
    _update(variable.get())
    variable.trace_add(_update)

def AdwSwitchRow(title: str, variable: ConfigVar, subtitle: str | None = None) -> Adw.SwitchRow:
    """A switch row bound to a ConfigVar."""
    row = Adw.SwitchRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_active(bool(variable.get()))
    row.connect("notify::active", lambda r, _p: variable.set(r.get_active()))

    # Reflect external changes (preset / pack-config apply) back into the widget,
    # guarded so the widget's own write-back doesn't loop.
    def _sync(value: object) -> None:
        active = bool(value)
        if row.get_active() != active:
            row.set_active(active)
    variable.trace_add(_sync)
    variable.widget = row
    return row


def _fmt_unit(raw: float, factor: float, unit: str | None) -> str:
    """Format a raw slider value in human units, rounded to a whole number,
    e.g. 60000ms -> '60 s', 6572ms -> '7 s'."""
    text = str(round(raw / factor))
    return f"{text} {unit}" if unit else text


def AdwSliderRow(title: str, variable: ConfigVar, from_: int, to: int, subtitle: str | None = None,
                 *, unit: str | None = None, factor: float = 1) -> Adw.ActionRow:
    """An ActionRow with an inline slider + spin button bound to a ConfigVar
    through a shared adjustment. The valid range shows as the subtitle.

    The adjustment stays in the stored (raw) unit so danger checks and save
    transforms are unaffected; `unit`/`factor` only change how the value is
    *displayed* (shown = raw / factor, with `unit` appended). e.g. a delay
    stored in ms shows as seconds with unit='s', factor=1000."""
    row = Adw.ActionRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    elif unit:
        row.set_subtitle(f"{_fmt_unit(from_, factor, unit)} – {_fmt_unit(to, factor, unit)}")
    else:
        row.set_subtitle(f"{from_}–{to}")

    adj = Gtk.Adjustment(value=variable.get(), lower=from_, upper=to, step_increment=1)
    if unit:
        # Step by one whole display unit (e.g. 1 s = 1000 ms) so +/- is sensible.
        adj.set_step_increment(factor)
        adj.set_page_increment(factor * 10)
    adj.connect("value-changed", lambda a: variable.set(int(a.get_value())))

    scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
    scale.set_draw_value(False)
    scale.set_digits(0)
    scale.set_hexpand(True)
    scale.set_size_request(180, -1)
    scale.set_valign(Gtk.Align.CENTER)

    spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
    spin.set_valign(Gtk.Align.CENTER)
    if unit:
        # Show the value in friendly units (e.g. "5 s"); typed input is read in
        # that same unit and converted back to the raw stored value.
        import re
        spin.set_numeric(False)
        spin.set_width_chars(7)

        def _output(s) -> bool:
            s.set_text(_fmt_unit(s.get_value(), factor, unit))
            return True

        def _input(s):
            m = re.search(r"-?\d+(?:\.\d+)?", s.get_text())
            if not m:
                return (False, 0.0)
            return (True, float(m.group()) * factor)
        spin.connect("output", _output)
        spin.connect("input", _input)
    else:
        spin.set_numeric(True)

    # Reflect external changes (preset / pack apply / danger revert) into the
    # slider. Force the scale's value too: after a programmatic adjustment set
    # the Range can fail to repaint the thumb (the spin updates, the scale
    # doesn't), so set it explicitly.
    def _sync(value: object) -> None:
        try:
            v = int(value)
        except (TypeError, ValueError):
            return
        if int(adj.get_value()) != v:
            adj.set_value(v)
            scale.set_value(v)
    variable.trace_add(_sync)

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_hexpand(True)
    box.append(scale)
    box.append(spin)
    row.add_suffix(box)
    variable.widget = row
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

    # Reflect external changes (preset / pack-config apply) into the combo.
    def _sync(value: object) -> None:
        if value in keys:
            idx = keys.index(value)
            if row.get_selected() != idx:
                row.set_selected(idx)
            row.set_subtitle(options.get(str(value), ""))
    variable.trace_add(_sync)
    variable.widget = row
    return row


def AdwEntryRow(title: str, variable: ConfigVar, password: bool = False) -> Adw.EntryRow:
    """A text (or masked password) entry row bound to a ConfigVar."""
    row = Adw.PasswordEntryRow(title=title) if password else Adw.EntryRow(title=title)
    row.set_text(str(variable.get() or ""))
    row.connect("changed", lambda r: variable.set(r.get_text()))

    # Reflect external changes (preset / pack-config apply) into the entry.
    def _sync(value: object) -> None:
        text = str(value or "")
        if row.get_text() != text:
            row.set_text(text)
    variable.trace_add(_sync)
    variable.widget = row
    return row
