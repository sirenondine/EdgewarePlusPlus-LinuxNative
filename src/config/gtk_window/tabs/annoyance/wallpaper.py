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

import logging
import os

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import GdkPixbuf, Gtk

from config.gtk_window.widgets import ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.gtk_window.toast import name_popover, toast
from config.gtk_window.utils import config
from config.vars import Vars
from os_utils import get_wallpaper
from pack import Pack
from paths import CustomAssets, Data

ROTATE_TEXT = "Turning on wallpaper rotate disables built-in pack wallpapers, allowing you to cycle through your own."
PANIC_TEXT = "Set your panic wallpaper to your default wallpaper ASAP!"


class WallpaperTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._vars = vars
        self._pack = pack

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        panic_section = ConfigSection("Panic Wallpaper", PANIC_TEXT)
        vbox.append(panic_section)

        self._panic_preview = Gtk.Picture()
        self._panic_preview.set_size_request(200, 112)
        self._load_panic_preview()
        panic_section.append(self._panic_preview)

        panic_btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        panic_section.append(panic_btn_row)

        set_btn = Gtk.Button(label="Set Panic Wallpaper")
        set_btn.set_tooltip_text("Set the wallpaper shown when you panic.")
        set_btn.connect("clicked", self._on_set_panic)
        panic_btn_row.append(set_btn)

        auto_btn = Gtk.Button(label="Auto Import")
        auto_btn.set_tooltip_text("Automatically set your current wallpaper as the panic wallpaper.")
        auto_btn.connect("clicked", self._on_auto_import_panic)
        panic_btn_row.append(auto_btn)

        rot_section = ConfigSection("Rotating Wallpaper", ROTATE_TEXT)
        vbox.append(rot_section)

        rot_row = ConfigRow()
        rot_section.append(rot_row)
        rot_toggle = ConfigToggle("Rotate Wallpapers", vars.rotate_wallpaper)
        rot_row.append(rot_toggle)

        self._wallpaper_store = Gtk.StringList.new(list(config.get("wallpaperDat", {}).keys()))
        self._wallpaper_list = Gtk.ListView.new(Gtk.SingleSelection.new(self._wallpaper_store))
        self._wallpaper_list.set_vexpand(True)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_list_item_setup)
        factory.connect("bind", self._on_list_item_bind)
        self._wallpaper_list.set_factory(factory)
        rot_section.append(self._wallpaper_list)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        rot_section.append(btn_row)

        add_btn = Gtk.Button(label="Add/Edit Wallpaper")
        add_btn.connect("clicked", self._on_add)
        btn_row.append(add_btn)

        remove_btn = Gtk.Button(label="Remove Wallpaper")
        remove_btn.connect("clicked", self._on_remove)
        btn_row.append(remove_btn)

        auto_wall_btn = Gtk.Button(label="Auto Import")
        auto_wall_btn.connect("clicked", self._on_auto_import)
        btn_row.append(auto_wall_btn)

        rot_row2 = ConfigRow()
        rot_section.append(rot_row2)
        rot_row2.append(ConfigScale("Rotate Timer (sec)", vars.wallpaper_timer, 5, 300))
        rot_row2.append(ConfigScale("Rotate Variation (sec)", vars.wallpaper_variance, 0, 300))

    def _on_set_panic(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Select Panic Wallpaper")
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        fd.set_default_filter(filt)
        fd.open(None, self._on_panic_file_selected, None)

    def _on_panic_file_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        from PIL import Image
        try:
            file = fd.open_finish(result)
            if not file:
                return
            path = file.get_path()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            pixbuf = pixbuf.scale_simple(200, 112, GdkPixbuf.InterpType.BILINEAR)
            self._panic_preview.set_pixbuf(pixbuf)
            Image.open(path).convert("RGB").save(Data.PANIC_WALLPAPER)
        except Exception as e:
            logging.warning(f"Failed to set panic wallpaper: {e}")

    def _on_auto_import_panic(self, _btn: Gtk.Button) -> None:
        try:
            from PIL import Image
            Image.open(get_wallpaper()).convert("RGB").save(Data.PANIC_WALLPAPER)
            self._load_panic_preview()
        except Exception as e:
            logging.warning(f"Failed to auto import panic wallpaper: {e}")

    def _load_panic_preview(self) -> None:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(CustomAssets.panic_wallpaper()), 200, 112)
            self._panic_preview.set_pixbuf(pixbuf)
        except Exception:
            pass

    def _on_add(self, btn: Gtk.Button) -> None:
        self._add_btn_anchor = btn
        self._pending_path = None
        fd = Gtk.FileDialog.new()
        fd.set_title("Select Wallpaper")
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        fd.set_default_filter(filt)
        fd.open(None, self._on_add_file_selected, None)

    def _on_add_file_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        try:
            file = fd.open_finish(result)
            if not file:
                return
            self._pending_path = file.get_path()
            name_popover(self._add_btn_anchor, "Wallpaper label", self._finish_add)
        except Exception:
            pass

    def _finish_add(self, name: str) -> None:
        if self._pending_path:
            wallpaper_dat = config.get("wallpaperDat", {})
            wallpaper_dat[name] = os.path.basename(self._pending_path)
            config["wallpaperDat"] = wallpaper_dat
            self._wallpaper_store.append(name)
            self._pending_path = None

    def _on_remove(self, _btn: Gtk.Button) -> None:
        selection = self._wallpaper_list.get_model()
        if isinstance(selection, Gtk.SingleSelection):
            pos = selection.get_selected()
            if pos != Gtk.INVALID_LIST_POSITION and pos > 0:
                name = self._wallpaper_store.get_string(pos)
                wallpaper_dat = config.get("wallpaperDat", {})
                if name in wallpaper_dat:
                    del wallpaper_dat[name]
                    config["wallpaperDat"] = wallpaper_dat
                self._wallpaper_store.remove(pos)

    def _on_auto_import(self, _btn: Gtk.Button) -> None:
        while self._wallpaper_store.get_n_items() > 0:
            self._wallpaper_store.remove(0)
        config["wallpaperDat"] = {}
        for f in os.listdir(self._pack.paths.root):
            if f.lower().endswith((".png", ".jpg", ".jpeg")) and f != "wallpaper.png":
                name = os.path.splitext(f)[0]
                self._wallpaper_store.append(name)
                config["wallpaperDat"][name] = f

    @staticmethod
    def _on_list_item_setup(_factory, item) -> None:
        label = Gtk.Label()
        label.set_xalign(0)
        item.set_child(label)

    @staticmethod
    def _on_list_item_bind(_factory, item) -> None:
        label = item.get_child()
        label.set_text(item.get_item().get_string())
