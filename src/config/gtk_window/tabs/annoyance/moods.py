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

import json
import logging

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.gtk_window.utils import config
from config.gtk_window.widgets import ConfigSection
from pack import Pack

MOOD_TEXT = (
    "Moods are a very important part of edgeware. Every piece of media has a mood attached to it, "
    "and edgeware checks to see if that mood is enabled before deciding to show it.\n\n"
    "In this tab you can disable or enable moods."
)


class MoodsTab(Gtk.ScrolledWindow):
    def __init__(self, pack: Pack) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        section = ConfigSection("Moods", MOOD_TEXT)
        vbox.append(section)

        mood_list = Gtk.ListBox(css_classes=["mood-list"])
        mood_list.set_vexpand(True)
        section.append(mood_list)

        active_moods = []
        if not config.get("toggleMoodSet"):
            try:
                with open(pack.info.mood_file, "r") as f:
                    active_moods = json.loads(f.read()).get("active", [])
            except Exception as e:
                logging.warning(f"error reading mood file: {e}")

        self._mood_switches: list[Gtk.Switch] = []
        has_moods = False
        for mood in pack.index.moods:
            assert mood.name is not None
            has_moods = True
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_child(hbox)

            switch = Gtk.Switch()
            switch.set_active(mood.name in active_moods)
            switch.connect("notify::active", self._make_mood_callback(pack, mood.name))
            self._mood_switches.append(switch)
            hbox.append(switch)

            lbl = Gtk.Label(label=mood.name)
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            hbox.append(lbl)

            info_lbl = Gtk.Label(
                label=f"Media: {sum(1 for v in pack.index.media_moods.values() if v == mood.name)} | "
                f"Clicks: {mood.max_clicks} | Caps: {len(mood.captions)}",
                wrap=True,
            )
            info_lbl.set_xalign(0)
            info_lbl.add_css_class("caption")
            hbox.append(info_lbl)

            mood_list.append(row)

        if not has_moods:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No moods found in pack!"))
            mood_list.append(row)

        if has_moods:
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            section.append(btn_row)
            select_all_btn = Gtk.Button(label="Select All")
            select_all_btn.connect("clicked", lambda _: self._set_all_moods(True))
            btn_row.append(select_all_btn)
            deselect_all_btn = Gtk.Button(label="Deselect All")
            deselect_all_btn.connect("clicked", lambda _: self._set_all_moods(False))
            btn_row.append(deselect_all_btn)

    def _set_all_moods(self, active: bool) -> None:
        for switch in self._mood_switches:
            switch.set_active(active)

    @staticmethod
    def _make_mood_callback(pack: Pack, mood_name: str):
        def callback(switch: Gtk.Switch, _param):
            if config.get("toggleMoodSet"):
                return
            try:
                with open(pack.info.mood_file, "r+") as f:
                    active = json.loads(f.read())
                    if switch.get_active():
                        if mood_name not in active["active"]:
                            active["active"].append(mood_name)
                    else:
                        if mood_name in active["active"]:
                            active["active"].remove(mood_name)
                    f.seek(0)
                    f.write(json.dumps(active))
                    f.truncate()
            except Exception as e:
                logging.warning(f"error updating mood file: {e}")

        return callback
