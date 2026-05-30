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
import shutil
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.widgets import AdwSliderRow, AdwSwitchRow
from config.gtk_window.toast import name_popover
from config.gtk_window.utils import config
from config.vars import Vars
from os_utils import get_wallpaper
from pack import Pack
from paths import CustomAssets, Data

ROTATE_TEXT = "Turning on wallpaper rotate disables built-in pack wallpapers, allowing you to cycle through your own."
PANIC_TEXT = "Set your panic wallpaper to your default wallpaper ASAP!"


class WallpaperTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()
        self._vars = vars
        self._pack = pack

        # ---- Panic wallpaper ---------------------------------------------
        panic = Adw.PreferencesGroup(title="Panic Wallpaper", description=PANIC_TEXT)
        self.add(panic)

        panic_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        set_btn = Gtk.Button(label="Set Panic Wallpaper")
        set_btn.set_tooltip_text("Set the wallpaper shown when you panic.")
        set_btn.connect("clicked", self._on_set_panic)
        panic_actions.append(set_btn)
        auto_btn = Gtk.Button(label="Auto Import")
        auto_btn.set_tooltip_text("Automatically set your current wallpaper as the panic wallpaper.")
        auto_btn.connect("clicked", self._on_auto_import_panic)
        panic_actions.append(auto_btn)
        panic.set_header_suffix(panic_actions)

        self._panic_preview = Gtk.Picture()
        self._panic_preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._panic_preview.set_can_shrink(True)
        self._panic_preview.set_size_request(-1, 240)
        self._load_panic_preview()
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(self._panic_preview)
        panic.add(frame)

        # ---- Rotating wallpaper ------------------------------------------
        rot = Adw.PreferencesGroup(title="Rotating Wallpaper", description=ROTATE_TEXT)
        self.add(rot)
        rot.add(AdwSwitchRow("Rotate Wallpapers", vars.rotate_wallpaper))

        rot_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button(label="Add/Edit")
        add_btn.connect("clicked", self._on_add)
        rot_actions.append(add_btn)
        self._wall_remove_btn = Gtk.Button(label="Remove")
        self._wall_remove_btn.connect("clicked", self._on_remove)
        self._wall_remove_btn.set_sensitive(False)
        rot_actions.append(self._wall_remove_btn)
        auto_wall_btn = Gtk.Button(label="Auto Import")
        auto_wall_btn.connect("clicked", self._on_auto_import)
        rot_actions.append(auto_wall_btn)
        rot.set_header_suffix(rot_actions)

        self._wallpaper_store = Gtk.StringList.new(list(config.get("wallpaperDat", {}).keys()))
        self._wallpaper_selection = Gtk.SingleSelection.new(self._wallpaper_store)
        self._wallpaper_selection.connect("notify::selected", self._update_remove_btn)
        self._wallpaper_list = Gtk.ListView.new(self._wallpaper_selection)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_list_item_setup)
        factory.connect("bind", self._on_list_item_bind)
        self._wallpaper_list.set_factory(factory)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(220)
        scroller.set_child(self._wallpaper_list)
        list_frame = Gtk.Frame()
        list_frame.add_css_class("card")
        list_frame.set_child(scroller)
        rot.add(list_frame)

        rot.add(AdwSliderRow("Rotate Timer (sec)", vars.wallpaper_timer, 5, 300))
        rot.add(AdwSliderRow("Rotate Variation (sec)", vars.wallpaper_variance, 0, 300))

    def _on_set_panic(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Select Panic Wallpaper")
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        fd.set_default_filter(filt)
        fd.open(self.get_root(), None, self._on_panic_file_selected, None)

    def _on_panic_file_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        from PIL import Image
        try:
            file = fd.open_finish(result)
            if not file:
                return
            path = file.get_path()
            Image.open(path).convert("RGB").save(Data.PANIC_WALLPAPER)
            self._load_panic_preview()
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
        # Hand the Picture the full-resolution file so it scales crisply to the
        # display size, instead of a pre-shrunk pixbuf that upscales blurry.
        try:
            self._panic_preview.set_filename(str(CustomAssets.panic_wallpaper()))
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
        fd.open(self.get_root(), None, self._on_add_file_selected, None)

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
            src = Path(self._pending_path)
            # Runtime resolves rotating wallpapers as pack.paths.root / filename,
            # so the file must live in the pack root to play and to preview.
            dest = self._pack.paths.root / src.name
            try:
                if src.resolve() != dest.resolve():
                    shutil.copyfile(src, dest)
            except Exception as e:
                logging.warning(f"Failed to copy wallpaper into pack: {e}")
            wallpaper_dat = config.get("wallpaperDat", {})
            wallpaper_dat[name] = src.name
            config["wallpaperDat"] = wallpaper_dat
            self._wallpaper_store.append(name)
            self._pending_path = None

    def _update_remove_btn(self, selection, _param=None) -> None:
        self._wall_remove_btn.set_sensitive(
            selection.get_selected() != Gtk.INVALID_LIST_POSITION
        )

    def _on_remove(self, _btn: Gtk.Button) -> None:
        pos = self._wallpaper_selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION:
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
        self._update_remove_btn(self._wallpaper_selection)

    @staticmethod
    def _on_list_item_setup(_factory, item) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        thumb = Gtk.Picture()
        thumb.set_size_request(96, 54)
        thumb.set_content_fit(Gtk.ContentFit.COVER)
        thumb.set_can_shrink(True)
        thumb_frame = Gtk.Frame()
        thumb_frame.add_css_class("card")
        thumb_frame.set_valign(Gtk.Align.CENTER)
        thumb_frame.set_child(thumb)
        box.append(thumb_frame)

        label = Gtk.Label()
        label.set_xalign(0)
        label.set_valign(Gtk.Align.CENTER)
        box.append(label)

        item.set_child(box)

    def _on_list_item_bind(self, _factory, item) -> None:
        box = item.get_child()
        thumb_frame = box.get_first_child()
        thumb = thumb_frame.get_child()
        label = thumb_frame.get_next_sibling()

        name = item.get_item().get_string()
        label.set_text(name)

        filename = config.get("wallpaperDat", {}).get(name)
        path = self._pack.paths.root / filename if filename else None
        if path and path.is_file():
            thumb.set_filename(str(path))
        else:
            thumb.set_paintable(None)
