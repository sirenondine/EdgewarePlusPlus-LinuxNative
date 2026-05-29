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

from config.gtk_window.toast import name_popover
from config.gtk_window.utils import config
from config.gtk_window.widgets import ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.vars import Vars

DRIVE_TEXT = (
    "\"Fill Drive\" will attempt to fill your computer with as much porn from the currently "
    "loaded pack as possible.\n\n"
    "\"Replace Images\" will seek out folders with large numbers of pre-existing images and "
    "replace ALL of them with images from the currently loaded pack."
)
MISC_TEXT = (
    "Disable Panic Hotkey disables both the panic hotkey and system tray panic.\n"
    "Launch on PC Startup runs Edgeware when you start your computer.\n"
    "Show on Discord gives you a status on discord while you run Edgeware."
)
PANIC_LOCKOUT_TEXT = (
    "Makes it so you cannot panic for a specified duration.\n"
    "A safeword can be used to still use panic during this time."
)


class DangerousSettingsTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Panic lockout
        lockout_section = ConfigSection("Panic Lockout", PANIC_LOCKOUT_TEXT)
        vbox.append(lockout_section)

        lockout_row = ConfigRow()
        lockout_section.append(lockout_row)
        lockout_row.append(ConfigToggle("Enable Panic Lockout", vars.panic_lockout))

        safeword_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lockout_row.append(safeword_box)
        safeword_box.append(Gtk.Label(label="Emergency Safeword"))
        safeword_entry = Gtk.PasswordEntry()
        safeword_entry.set_text(str(vars.panic_lockout_password.get()))
        safeword_entry.connect("changed", lambda e: vars.panic_lockout_password.set(e.get_text()))
        safeword_box.append(safeword_entry)

        lockout_time_row = ConfigRow()
        lockout_section.append(lockout_time_row)
        lockout_time_row.append(
            ConfigScale("Panic Lockout Time (minutes)", vars.panic_lockout_time, 1, 1440)
        )

        # Drive
        drive_section = ConfigSection("Hard Drive Settings", DRIVE_TEXT)
        vbox.append(drive_section)

        drive_frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        drive_section.append(drive_frame)

        # Blacklist
        bl_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        drive_frame.append(bl_frame)
        bl_frame.append(Gtk.Label(label="Folder Name Blacklist"))

        avoid_list = config.get("avoidList", "Edgeware>AppData").split(">")
        self._bl_store = Gtk.StringList.new(avoid_list)
        self._bl_list = Gtk.ListView.new(Gtk.SingleSelection.new(self._bl_store))
        self._bl_list.set_vexpand(True)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda f, i: i.set_child(Gtk.Label(xalign=0, wrap=True)))
        factory.connect("bind", lambda f, i: i.get_child().set_text(i.get_item().get_string()))
        self._bl_list.set_factory(factory)
        bl_frame.append(self._bl_list)

        bl_btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bl_frame.append(bl_btn_col)

        add_btn = Gtk.Button(label="Add Name")
        add_btn.connect("clicked", self._on_add_blacklist)
        bl_btn_col.append(add_btn)

        remove_btn = Gtk.Button(label="Remove Name")
        remove_btn.connect("clicked", self._on_remove_blacklist)
        bl_btn_col.append(remove_btn)

        reset_btn = Gtk.Button(label="Reset")
        reset_btn.connect("clicked", self._on_reset_blacklist)
        bl_btn_col.append(reset_btn)

        # Fill/Replace
        fr_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        drive_frame.append(fr_frame)

        fill_toggle = ConfigToggle("Fill Drive", vars.fill_drive,
            tooltip="Attempts to fill your hard drive with images from /resource/img/.")
        fr_frame.append(fill_toggle)

        fill_scale = ConfigScale("Fill Delay (10ms)", vars.fill_delay, 0, 250)
        fr_frame.append(fill_scale)

        replace_toggle = ConfigToggle("Replace Images", vars.replace_images,
            tooltip="Seeks out folders with more images than the threshold value, then replaces all.")
        fr_frame.append(replace_toggle)

        replace_scale = ConfigScale("Image Threshold", vars.replace_threshold, 1, 1000)
        fr_frame.append(replace_scale)

        # Path
        path_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        drive_section.append(path_frame)
        path_frame.append(Gtk.Label(label="Fill/Replace Start Folder"))
        self._path_entry = Gtk.Entry()
        self._path_entry.set_text(config.get("drivePath", ""))
        self._path_entry.set_editable(False)
        path_frame.append(self._path_entry)
        select_btn = Gtk.Button(label="Select")
        select_btn.connect("clicked", self._on_select_path)
        path_frame.append(select_btn)

        # Misc
        misc_section = ConfigSection("Misc. Dangerous Settings", MISC_TEXT)
        vbox.append(misc_section)

        misc_row = ConfigRow()
        misc_section.append(misc_row)
        misc_row.append(
            ConfigToggle("Disable Panic Hotkey", vars.panic_disabled,
                tooltip="Also disables panic in the system tray.")
        )
        misc_row.append(ConfigToggle("Launch on PC Startup", vars.run_at_startup))
        misc_row.append(
            ConfigToggle("Show on Discord", vars.show_on_discord,
                tooltip="Displays a lewd status on discord.")
        )

    def _on_add_blacklist(self, btn: Gtk.Button) -> None:
        name_popover(btn, "Folder name to skip", self._add_blacklist_name)

    def _add_blacklist_name(self, name: str) -> None:
        current = config.get("avoidList", "Edgeware>AppData")
        config["avoidList"] = f"{current}>{name}"
        self._bl_store.append(name)

    def _on_remove_blacklist(self, _btn: Gtk.Button) -> None:
        selection = self._bl_list.get_model()
        if isinstance(selection, Gtk.SingleSelection):
            pos = selection.get_selected()
            if pos != Gtk.INVALID_LIST_POSITION and pos > 0:
                name = self._bl_store.get_string(pos)
                current = config.get("avoidList", "")
                config["avoidList"] = current.replace(f">{name}", "")
                self._bl_store.remove(pos)

    def _on_reset_blacklist(self, _btn: Gtk.Button) -> None:
        while self._bl_store.get_n_items() > 0:
            self._bl_store.remove(0)
        for item in ["Edgeware", "AppData"]:
            self._bl_store.append(item)
        config["avoidList"] = "Edgeware>AppData"

    def _on_select_path(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Select Parent Folder")
        fd.select_folder(None, self._on_folder_selected, None)

    def _on_folder_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        try:
            file = fd.select_folder_finish(result)
            if not file:
                return
            path = file.get_path()
            config["drivePath"] = path
            self._path_entry.set_text(path)
        except Exception:
            pass
