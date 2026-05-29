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

from config.gtk_window import name_popover

from config.gtk_window.utils import config
from config.gtk_window.widgets import ConfigRow, ConfigSection, ConfigToggle
from config.vars import Vars

BOORU_TEXT = (
    "The \"Booru Downloader\" is not currently in a great state. "
    "It can lead to performance issues and is not guaranteed to work in the future."
)


class BooruTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        section = ConfigSection("Booru Settings", BOORU_TEXT)
        vbox.append(section)

        download_row = ConfigRow()
        section.append(download_row)
        section.append(ConfigToggle("Download from Booru", vars.booru_download))

        tag_row = ConfigRow()
        section.append(tag_row)

        tags = config.get("tagList", "").split(">")
        self._tag_store = Gtk.StringList.new(tags)
        self._tag_list = Gtk.ListView.new(Gtk.SingleSelection.new(self._tag_store))
        self._tag_list.set_vexpand(True)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda f, i: i.set_child(Gtk.Label(xalign=0, wrap=True)))
        factory.connect("bind", lambda f, i: i.get_child().set_text(i.get_item().get_string()))
        self._tag_list.set_factory(factory)
        tag_row.append(self._tag_list)

        btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        tag_row.append(btn_col)

        add_btn = Gtk.Button(label="Add Tag")
        add_btn.connect("clicked", self._on_add)
        btn_col.append(add_btn)

        remove_btn = Gtk.Button(label="Remove Tag")
        remove_btn.connect("clicked", self._on_remove)
        btn_col.append(remove_btn)

        reset_btn = Gtk.Button(label="Reset Tags")
        reset_btn.connect("clicked", self._on_reset)
        btn_col.append(reset_btn)

    def _on_add(self, btn: Gtk.Button) -> None:
        name_popover(btn, "Tag name (or space-separated tags)", self._add_tag)

    def _add_tag(self, tag: str) -> None:
        current = config.get("tagList", "")
        config["tagList"] = f"{current}>{tag}" if current else tag
        self._tag_store.append(tag)

    def _on_remove(self, _btn: Gtk.Button) -> None:
        selection = self._tag_list.get_model()
        if isinstance(selection, Gtk.SingleSelection):
            pos = selection.get_selected()
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
