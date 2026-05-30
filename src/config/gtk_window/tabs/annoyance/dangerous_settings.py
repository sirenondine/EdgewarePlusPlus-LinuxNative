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

import os
import platform

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.toast import name_popover
from config.gtk_window.utils import config
from config.gtk_window.widgets import AdwSliderRow, AdwSwitchRow
from config.vars import Vars

DRIVE_TEXT = (
    "\"Fill Drive\" attempts to fill your computer with as much content from the "
    "current pack as possible. \"Replace Images\" seeks folders with large numbers "
    "of existing images and replaces ALL of them with pack content."
)
PANIC_LOCKOUT_TEXT = (
    "Prevents panic for a set duration. A safeword allows panic during lockout."
)
MISC_TEXT = (
    "Disable Panic Hotkey also disables panic in the system tray. "
    "Show on Discord displays a status while Edgeware is running."
)


class DangerousSettingsTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        # ---- Panic lockout -----------------------------------------------
        lockout = Adw.PreferencesGroup(title="Panic Lockout", description=PANIC_LOCKOUT_TEXT)
        self.add(lockout)
        lockout.add(AdwSwitchRow("Enable Panic Lockout", vars.panic_lockout))

        safeword_row = Adw.ActionRow(title="Emergency Safeword")
        entry = Gtk.PasswordEntry()
        entry.set_show_peek_icon(True)
        entry.set_text(str(vars.panic_lockout_password.get()))
        entry.set_valign(Gtk.Align.CENTER)
        entry.connect("changed", lambda e: vars.panic_lockout_password.set(e.get_text()))
        safeword_row.add_suffix(entry)
        lockout.add(safeword_row)
        lockout.add(AdwSliderRow("Lockout Duration (minutes)", vars.panic_lockout_time, 1, 1440))

        # ---- Misc. dangerous ---------------------------------------------
        misc = Adw.PreferencesGroup(title="Misc. Dangerous Settings", description=MISC_TEXT)
        self.add(misc)
        misc.add(AdwSwitchRow(
            "Disable Panic Hotkey", vars.panic_disabled,
            subtitle="Also disables panic in the system tray."))
        misc.add(AdwSwitchRow("Launch on PC Startup", vars.run_at_startup))
        misc.add(AdwSwitchRow(
            "Show on Discord", vars.show_on_discord,
            subtitle="Displays a lewd status on Discord while Edgeware is running."))

        # ---- Hard drive settings -----------------------------------------
        drive = Adw.PreferencesGroup(title="Hard Drive Settings", description=DRIVE_TEXT)
        self.add(drive)
        drive.add(AdwSwitchRow(
            "Fill Drive", vars.fill_drive,
            subtitle="Fills your hard drive with images from the pack."))
        drive.add(AdwSliderRow("Fill Delay (×10 ms)", vars.fill_delay, 0, 250))
        drive.add(AdwSwitchRow(
            "Replace Images", vars.replace_images,
            subtitle="Replaces existing images in folders that exceed the threshold."))
        drive.add(AdwSliderRow("Image Threshold", vars.replace_threshold, 1, 1000))

        # Fill/Replace start folder
        drive_path = config.get("drivePath", "")
        if platform.system() == "Linux" and drive_path in ("C:/Users/", "C:\\Users\\"):
            drive_path = os.path.expanduser("~")

        path_row = Adw.ActionRow(
            title="Fill/Replace Start Folder",
            subtitle=drive_path or "Not set",
        )
        self._path_row = path_row
        select_btn = Gtk.Button(icon_name="folder-open-symbolic")
        select_btn.set_tooltip_text("Choose the folder Fill Drive and Replace Images will start from")
        select_btn.set_valign(Gtk.Align.CENTER)
        select_btn.connect("clicked", self._on_select_path)
        path_row.add_suffix(select_btn)
        path_row.set_activatable_widget(select_btn)
        drive.add(path_row)

        # ---- Folder blacklist --------------------------------------------
        blacklist = Adw.PreferencesGroup(
            title="Folder Name Blacklist",
            description="Folder names that Fill Drive and Replace Images will skip.",
        )
        self.add(blacklist)

        avoid_list = [t for t in config.get("avoidList", "Edgeware>AppData").split(">") if t]
        self._bl_store = Gtk.StringList.new(avoid_list)
        self._bl_selection = Gtk.SingleSelection.new(self._bl_store)
        self._bl_selection.connect("notify::selected", self._update_bl_btn)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_bl_setup)
        factory.connect("bind", self._on_bl_bind)
        bl_list = Gtk.ListView.new(self._bl_selection, factory)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(140)
        scroller.set_child(bl_list)
        list_frame = Gtk.Frame()
        list_frame.add_css_class("card")
        list_frame.set_child(scroller)
        blacklist.add(list_frame)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add a folder name to skip")
        add_btn.connect("clicked", self._on_add_blacklist)
        btn_row.append(add_btn)
        self._bl_remove_btn = Gtk.Button(icon_name="list-remove-symbolic")
        self._bl_remove_btn.set_tooltip_text("Remove selected folder name")
        self._bl_remove_btn.set_sensitive(False)
        self._bl_remove_btn.connect("clicked", self._on_remove_blacklist)
        btn_row.append(self._bl_remove_btn)
        reset_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        reset_btn.set_tooltip_text("Reset blacklist to defaults")
        reset_btn.connect("clicked", self._on_reset_blacklist)
        btn_row.append(reset_btn)
        blacklist.set_header_suffix(btn_row)

    def _on_select_path(self, _btn) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Select Parent Folder")
        fd.select_folder(self.get_root(), None, self._on_folder_selected, None)

    def _on_folder_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        try:
            file = fd.select_folder_finish(result)
            if not file:
                return
            path = file.get_path()
            config["drivePath"] = path
            self._path_row.set_subtitle(path)
        except Exception:
            pass

    def _on_add_blacklist(self, btn: Gtk.Button) -> None:
        name_popover(btn, "Folder name to skip", self._add_blacklist_name)

    def _add_blacklist_name(self, name: str) -> None:
        current = config.get("avoidList", "Edgeware>AppData")
        config["avoidList"] = f"{current}>{name}"
        self._bl_store.append(name)

    def _update_bl_btn(self, selection, _param=None) -> None:
        pos = selection.get_selected()
        self._bl_remove_btn.set_sensitive(
            pos != Gtk.INVALID_LIST_POSITION and pos > 0
        )

    def _on_remove_blacklist(self, _btn) -> None:
        pos = self._bl_selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION and pos > 0:
            name = self._bl_store.get_string(pos)
            current = config.get("avoidList", "")
            config["avoidList"] = current.replace(f">{name}", "")
            self._bl_store.remove(pos)

    def _on_reset_blacklist(self, _btn) -> None:
        while self._bl_store.get_n_items() > 0:
            self._bl_store.remove(0)
        for item in ["Edgeware", "AppData"]:
            self._bl_store.append(item)
        config["avoidList"] = "Edgeware>AppData"

    @staticmethod
    def _on_bl_setup(_factory, item) -> None:
        lbl = Gtk.Label(xalign=0, wrap=True)
        lbl.set_margin_start(8)
        lbl.set_margin_top(4)
        lbl.set_margin_bottom(4)
        item.set_child(lbl)

    @staticmethod
    def _on_bl_bind(_factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())
