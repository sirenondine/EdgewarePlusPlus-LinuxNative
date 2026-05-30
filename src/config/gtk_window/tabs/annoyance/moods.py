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
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.utils import config
from pack import Pack

MOOD_TEXT = (
    "Every piece of media has a mood attached to it. Edgeware checks whether that "
    "mood is enabled before deciding to show it. Disable moods here to filter content."
)


class MoodsTab(Adw.PreferencesPage):
    def __init__(self, pack: Pack) -> None:
        super().__init__()

        group = Adw.PreferencesGroup(title="Moods", description=MOOD_TEXT)
        self.add(group)

        active_moods = []
        if not config.get("toggleMoodSet"):
            try:
                with open(pack.info.mood_file, "r") as f:
                    active_moods = json.loads(f.read()).get("active", [])
            except Exception as e:
                logging.warning(f"error reading mood file: {e}")

        self._mood_rows: list[Adw.SwitchRow] = []
        has_moods = False

        for mood in pack.index.moods:
            assert mood.name is not None
            has_moods = True

            media_count = sum(1 for v in pack.index.media_moods.values() if v == mood.name)
            row = Adw.SwitchRow(
                title=mood.name,
                subtitle=f"{media_count} media · {mood.max_clicks} max clicks · {len(mood.captions)} captions",
            )
            row.set_active(mood.name in active_moods)
            row.connect("notify::active", self._make_mood_callback(pack, mood.name))
            self._mood_rows.append(row)
            group.add(row)

        if not has_moods:
            empty = Adw.ActionRow(title="No moods found in this pack.")
            empty.set_sensitive(False)
            group.add(empty)

        if has_moods:
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            select_all = Gtk.Button(icon_name="object-select-symbolic")
            select_all.set_tooltip_text("Select all moods")
            select_all.connect("clicked", lambda _: self._set_all(True))
            deselect_all = Gtk.Button(icon_name="edit-clear-all-symbolic")
            deselect_all.set_tooltip_text("Deselect all moods")
            deselect_all.connect("clicked", lambda _: self._set_all(False))
            btn_row.append(select_all)
            btn_row.append(deselect_all)
            group.set_header_suffix(btn_row)

    def _set_all(self, active: bool) -> None:
        for row in self._mood_rows:
            row.set_active(active)

    @staticmethod
    def _make_mood_callback(pack: Pack, mood_name: str):
        def callback(row: Adw.SwitchRow, _param):
            if config.get("toggleMoodSet"):
                return
            try:
                with open(pack.info.mood_file, "r+") as f:
                    data = json.loads(f.read())
                    if row.get_active():
                        if mood_name not in data["active"]:
                            data["active"].append(mood_name)
                    else:
                        if mood_name in data["active"]:
                            data["active"].remove(mood_name)
                    f.seek(0)
                    f.write(json.dumps(data))
                    f.truncate()
            except Exception as e:
                logging.warning(f"error updating mood file: {e}")

        return callback
