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

from config.gtk_window.toast import name_popover
from config.gtk_window.utils import config
from config.gtk_window.widgets import AdwSwitchRow
from config.vars import Vars

BOORU_TEXT = (
    "The Booru Downloader is not currently in a great state — it can cause "
    "performance issues and is not guaranteed to work in the future."
)


class BooruTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        group = Adw.PreferencesGroup(title="Booru Settings", description=BOORU_TEXT)
        self.add(group)
        group.add(AdwSwitchRow("Download from Booru", vars.booru_download))

        tags_group = Adw.PreferencesGroup(title="Tags")
        self.add(tags_group)

        tags = [t for t in config.get("tagList", "").split(">") if t]
        self._tag_store = Gtk.StringList.new(tags)
        self._tag_selection = Gtk.SingleSelection.new(self._tag_store)
        self._tag_selection.connect("notify::selected", self._update_buttons)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        tag_list = Gtk.ListView.new(self._tag_selection, factory)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(180)
        scroller.set_child(tag_list)
        list_frame = Gtk.Frame()
        list_frame.add_css_class("card")
        list_frame.set_child(scroller)
        tags_group.add(list_frame)

        # Header suffix buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add)
        btn_row.append(add_btn)
        self._remove_btn = Gtk.Button(label="Remove")
        self._remove_btn.connect("clicked", self._on_remove)
        self._remove_btn.set_sensitive(False)
        btn_row.append(self._remove_btn)
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.connect("clicked", self._on_reset)
        btn_row.append(reset_btn)
        tags_group.set_header_suffix(btn_row)

    def _on_add(self, btn: Gtk.Button) -> None:
        name_popover(btn, "Tag name (or space-separated tags)", self._add_tag)

    def _add_tag(self, tag: str) -> None:
        current = config.get("tagList", "")
        config["tagList"] = f"{current}>{tag}" if current else tag
        self._tag_store.append(tag)

    def _update_buttons(self, selection, _param=None) -> None:
        pos = selection.get_selected()
        # pos 0 is "all" — don't allow removing it
        self._remove_btn.set_sensitive(
            pos != Gtk.INVALID_LIST_POSITION and pos > 0
        )

    def _on_remove(self, _btn: Gtk.Button) -> None:
        pos = self._tag_selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION and pos > 0:
            tag = self._tag_store.get_string(pos)
            current = config.get("tagList", "")
            config["tagList"] = current.replace(f">{tag}", "")
            self._tag_store.remove(pos)

    def _on_reset(self, _btn: Gtk.Button) -> None:
        while self._tag_store.get_n_items() > 0:
            self._tag_store.remove(0)
        self._tag_store.append("all")
        config["tagList"] = "all"

    @staticmethod
    def _on_setup(_factory, item) -> None:
        lbl = Gtk.Label(xalign=0, wrap=True)
        lbl.set_margin_start(8)
        lbl.set_margin_top(4)
        lbl.set_margin_bottom(4)
        item.set_child(lbl)

    @staticmethod
    def _on_bind(_factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())
