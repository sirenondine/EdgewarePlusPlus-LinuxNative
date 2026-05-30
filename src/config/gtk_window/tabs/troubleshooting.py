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
require_version("Adw", "1")
from gi.repository import Adw, Gtk

import os_utils
import utils
from config.gtk_window.utils import log_file, request_legacy_panic_key
from config.gtk_window.widgets import AdwSwitchRow
from config.vars import Vars
from pack import Pack
from paths import Data


class TroubleshootingTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()

        # ---- Troubleshooting toggles -------------------------------------
        ts = Adw.PreferencesGroup(title="Troubleshooting")
        self.add(ts)
        ts.add(AdwSwitchRow(
            "Toggle Tray Hibernate Skip", vars.toggle_hibernate_skip,
            subtitle="Adds a tray option to skip to the start of hibernate."))
        ts.add(AdwSwitchRow(
            "Turn Off Mood Settings", vars.toggle_mood_set,
            subtitle="Disables mood saving — useful when rapidly editing your pack."))
        ts.add(AdwSwitchRow(
            "Disable Connection to GitHub", vars.toggle_internet,
            subtitle="Disables all GitHub connections on future launches."))
        ts.add(AdwSwitchRow(
            "Enable Hardware Acceleration", vars.video_hardware_acceleration,
            subtitle="Disabling may increase CPU usage but gives a more consistent experience."))

        # ---- Legacy panic key -------------------------------------------
        legacy = Adw.PreferencesGroup(
            title="Legacy",
            description="The legacy panic key only works when an Edgeware popup has focus.",
        )
        self.add(legacy)

        from config.gtk_window.utils import pretty_panic_key
        legacy_row = Adw.ActionRow(
            title="Set Legacy Panic Key",
            subtitle="Requires focus on an Edgeware popup to fire.",
        )
        self._legacy_btn = Gtk.Button(label=f"<{pretty_panic_key(vars.panic_key.get())}>")
        self._legacy_btn.set_valign(Gtk.Align.CENTER)
        self._legacy_btn.connect(
            "clicked",
            lambda _: request_legacy_panic_key(self._legacy_btn, vars.panic_key),
        )
        legacy_row.add_suffix(self._legacy_btn)
        legacy_row.set_activatable_widget(self._legacy_btn)
        legacy.add(legacy_row)

        # ---- Logs --------------------------------------------------------
        logs = Adw.PreferencesGroup(title="Logs")
        self.add(logs)

        self._log_count_row = Adw.ActionRow(title="Log Files")
        self._log_count_row.set_subtitle(f"{self._get_log_number()} log files on disk")
        open_logs_btn = Gtk.Button(label="Open Folder")
        open_logs_btn.set_valign(Gtk.Align.CENTER)
        open_logs_btn.connect("clicked", lambda _: os_utils.open_directory(Data.LOGS))
        self._log_count_row.add_suffix(open_logs_btn)
        del_logs_btn = Gtk.Button(label="Delete All")
        del_logs_btn.set_valign(Gtk.Align.CENTER)
        del_logs_btn.add_css_class("destructive-action")
        del_logs_btn.set_tooltip_text("Deletes every log except the currently active one.")
        del_logs_btn.connect("clicked", lambda _: self._on_delete_logs())
        self._log_count_row.add_suffix(del_logs_btn)
        logs.add(self._log_count_row)

        # ---- Directories -------------------------------------------------
        dirs = Adw.PreferencesGroup(title="Directories")
        self.add(dirs)

        pack_id = pack.info.mood_file.with_suffix("").name
        using_unique = pack_id == utils.compute_mood_id(pack.paths)
        mood_row = Adw.ActionRow(
            title="Mood File ID",
            subtitle=pack_id,
        )
        id_lbl = Gtk.Label(label="✓" if using_unique else "✗")
        id_lbl.set_valign(Gtk.Align.CENTER)
        id_lbl.add_css_class("status-ok" if using_unique else "status-fail")
        id_lbl.set_tooltip_text("Using unique ID" if using_unique else "Not using unique ID")
        mood_row.add_suffix(id_lbl)
        open_moods_btn = Gtk.Button(label="Open Moods Folder")
        open_moods_btn.set_valign(Gtk.Align.CENTER)
        open_moods_btn.connect("clicked", lambda _: os_utils.open_directory(Data.MOODS))
        mood_row.add_suffix(open_moods_btn)
        dirs.add(mood_row)

        pack_row = Adw.ActionRow(title="Pack Folder", subtitle=str(pack.paths.root))
        open_pack_btn = Gtk.Button(label="Open")
        open_pack_btn.set_valign(Gtk.Align.CENTER)
        open_pack_btn.connect("clicked", lambda _: os_utils.open_directory(pack.paths.root))
        pack_row.add_suffix(open_pack_btn)
        pack_row.set_activatable_widget(open_pack_btn)
        dirs.add(pack_row)

    @staticmethod
    def _get_log_number() -> int:
        return len(os.listdir(Data.LOGS)) if os.path.exists(Data.LOGS) else 0

    def _on_delete_logs(self) -> None:
        from gtk_dialog import ask_yes_no
        if not ask_yes_no(
            "Delete Logs",
            f"Delete all logs? ({self._get_log_number()} total)\n"
            "The currently active log will be kept.",
            heading="Confirm deletion",
        ):
            return
        if not (os.path.exists(Data.LOGS) and os.listdir(Data.LOGS)):
            return
        try:
            for file in os.listdir(Data.LOGS):
                if os.path.splitext(file)[0] == os.path.splitext(log_file)[0]:
                    continue
                if os.path.splitext(file)[1].lower() == ".txt":
                    os.remove(Data.LOGS / file)
            self._log_count_row.set_subtitle(f"{self._get_log_number()} log files on disk")
        except Exception as e:
            logging.warning(f"could not clear logs: {e}")
