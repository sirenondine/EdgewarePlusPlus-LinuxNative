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
from gi.repository import Gtk

import os_utils
import utils
from config.gtk_window.utils import log_file, request_legacy_panic_key
from config.gtk_window.widgets import ConfigRow, ConfigSection, ConfigToggle
from config.vars import Vars
from pack import Pack
from paths import Data


class TroubleshootingTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Troubleshooting
        ts_section = ConfigSection("Troubleshooting")
        vbox.append(ts_section)

        row = ConfigRow()
        ts_section.append(row)
        row.append(
            ConfigToggle("Toggle Tray Hibernate Skip", vars.toggle_hibernate_skip,
                tooltip="Adds a tray feature to skip to the start of hibernate.")
        )
        row.append(
            ConfigToggle("Turn Off Mood Settings", vars.toggle_mood_set,
                tooltip="Disables mood saving if you're rapidly editing your pack.")
        )

        row2 = ConfigRow()
        ts_section.append(row2)
        row2.append(
            ConfigToggle("Disable Connection to GitHub", vars.toggle_internet,
                tooltip="Disables all connections to GitHub on future launches.")
        )
        row2.append(
            ConfigToggle("Run mpv in a Subprocess", vars.mpv_subprocess,
                tooltip="Fixes a crash when closing mpv on Linux/Windows.")
        )

        row3 = ConfigRow()
        ts_section.append(row3)
        row3.append(
            ConfigToggle("Enable hardware acceleration", vars.video_hardware_acceleration,
                tooltip="Disabling may increase CPU usage but provides more consistent experience.")
        )

        # Legacy
        legacy_section = ConfigSection("Legacy")
        vbox.append(legacy_section)

        self._legacy_btn = Gtk.Button(label=f"Set Legacy\nPanic Key\n<{vars.panic_key.get()}>")
        self._legacy_btn.set_tooltip_text(
            "Old panic key. Requires focus on an Edgeware popup."
        )
        self._legacy_btn.connect("clicked", lambda _: request_legacy_panic_key(self._legacy_btn, vars.panic_key))
        legacy_section.append(self._legacy_btn)

        # Directories
        dir_section = ConfigSection("Directories")
        vbox.append(dir_section)

        logs_frame = Gtk.Frame()
        logs_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        logs_frame.set_child(logs_hbox)
        dir_section.append(logs_frame)

        logs_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        logs_hbox.append(logs_col1)
        self._log_count_lbl = Gtk.Label(label=f"Total Logs: {self._get_log_number()}")
        logs_col1.append(self._log_count_lbl)

        logs_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        logs_hbox.append(logs_col2)
        open_logs_btn = Gtk.Button(label="Open Logs Folder")
        open_logs_btn.connect("clicked", lambda _: os_utils.open_directory(Data.LOGS))
        logs_col2.append(open_logs_btn)
        delete_logs_btn = Gtk.Button(label="Delete All Logs")
        delete_logs_btn.set_tooltip_text("Deletes every log except the currently written one.")
        delete_logs_btn.connect("clicked", lambda _: self._on_delete_logs())
        logs_col2.append(delete_logs_btn)

        moods_frame = Gtk.Frame()
        moods_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        moods_frame.set_child(moods_hbox)
        dir_section.append(moods_frame)

        moods_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        moods_hbox.append(moods_col1)

        pack_id = pack.info.mood_file.with_suffix("").name
        using_unique = pack_id == utils.compute_mood_id(pack.paths)
        id_lbl = Gtk.Label(label=("Using Unique ID?: " + ("\u2713" if using_unique else "\u2717")))
        id_lbl.add_css_class("status-ok" if using_unique else "status-fail")
        moods_col1.append(id_lbl)
        pack_id_lbl = Gtk.Label(label=f"Pack ID is: {pack_id}", wrap=True)
        pack_id_lbl.set_hexpand(True)
        moods_col1.append(pack_id_lbl)

        moods_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        moods_hbox.append(moods_col2)
        open_moods_btn = Gtk.Button(label="Open Moods Folder")
        open_moods_btn.set_tooltip_text("Opens the moods folder for the current pack.")
        open_moods_btn.connect("clicked", lambda _: os_utils.open_directory(Data.MOODS))
        moods_col2.append(open_moods_btn)

        open_pack_btn = Gtk.Button(label="Open Pack Folder")
        open_pack_btn.connect("clicked", lambda _: os_utils.open_directory(pack.paths.root))
        dir_section.append(open_pack_btn)

    @staticmethod
    def _get_log_number() -> int:
        return len(os.listdir(Data.LOGS)) if os.path.exists(Data.LOGS) else 0

    def _on_delete_logs(self) -> None:
        dialog = Gtk.MessageDialog(
            text="Confirm Delete",
            secondary_text=f"Are you sure you want to delete all logs? There are currently {self._get_log_number()}.",
            buttons=Gtk.ButtonsType.YES_NO,
            message_type=Gtk.MessageType.WARNING,
        )
        if dialog.run() != Gtk.ResponseType.YES:
            dialog.destroy()
            return
        dialog.destroy()

        if not (os.path.exists(Data.LOGS) and os.listdir(Data.LOGS)):
            return

        try:
            for file in os.listdir(Data.LOGS):
                if os.path.splitext(file)[0] == os.path.splitext(log_file)[0]:
                    continue
                if os.path.splitext(file)[1].lower() == ".txt":
                    os.remove(Data.LOGS / file)
            self._log_count_lbl.set_text(f"Total Logs: {self._get_log_number()}")
        except Exception as e:
            logging.warning(f"could not clear logs: {e}")
