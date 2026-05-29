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

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.gtk_window.preset import apply_preset
from config.gtk_window.utils import clear_launches
from config.gtk_window.widgets import ConfigDropdown, ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.vars import Vars
from pack import Pack

INTRO_TEXT = (
    "Corruption is a highly specialized mode that packs have to explicitly support. "
    "When corruption is enabled, it will turn off and on moods based on a trigger."
)
TRIGGER_TEXT = (
    "Triggers are the goals that define how corruption changes over time."
)
PATH_TEXT = (
    "Here is a chart that shows a basic view of the path that the currently loaded path "
    "will take during corruption."
)


class CorruptionModeTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Start
        start_section = ConfigSection("Corruption", INTRO_TEXT)
        vbox.append(start_section)

        start_row = ConfigRow()
        start_section.append(start_row)

        corruption_toggle = ConfigToggle("Turn on Corruption", vars.corruption_mode,
            tooltip="Corruption Mode gradually makes the pack more depraved.")
        start_row.append(corruption_toggle)
        has_corruption = os.path.isfile(pack.paths.corruption)
        corruption_toggle.set_sensitive(has_corruption)

        full_perm_toggle = ConfigToggle("Full Permissions Mode", vars.corruption_full,
            tooltip="Allows corruption mode to change config settings.")
        start_row.append(full_perm_toggle)

        recommended_btn = Gtk.Button(label="Recommended Settings")
        recommended_btn.set_tooltip_text("Pack creators can set default corruption settings.")
        recommended_btn.connect("clicked", lambda _: apply_preset(pack.config, vars, ["corruptionMode", "corruptionTime", "corruptionFadeType"]))
        start_section.append(recommended_btn)

        # Triggers
        triggers_section = ConfigSection("Triggers", TRIGGER_TEXT)
        vbox.append(triggers_section)

        trigger_row = ConfigRow()
        triggers_section.append(trigger_row)

        trigger_row.append(
            ConfigDropdown(
                vars.corruption_trigger,
                {
                    "Timed": "Transitions based on time elapsed.",
                    "Popup": "Transitions based on number of popups.",
                    "Launch": "Transitions based on number of launches.",
                    "Script": "Transitions handled by pack scripts.",
                },
            )
        )

        # Fade type
        fade_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        trigger_row.append(fade_frame)

        fade_types = ["Normal", "Abrupt"]
        fade_strings = Gtk.StringList.new(fade_types)
        fade_dropdown = Gtk.DropDown(model=fade_strings)
        current_fade = str(vars.corruption_fade.get())
        if current_fade in fade_types:
            fade_dropdown.set_selected(fade_types.index(current_fade))
        fade_dropdown.connect("notify::selected", lambda d, _: vars.corruption_fade.set(fade_types[d.get_selected()]))
        fade_frame.append(fade_dropdown)

        self._fade_desc = Gtk.Label(label="Gradually transitions between corruption levels.")
        self._fade_desc.set_wrap(True)
        fade_frame.append(self._fade_desc)

        fade_dropdown.connect("notify::selected", self._on_fade_changed)

        # Trigger scales
        triggers_row = ConfigRow()
        triggers_section.append(triggers_row)
        triggers_row.append(ConfigScale("Level Time (seconds)", vars.corruption_time, 5, 1800))
        triggers_row.append(ConfigScale("Level Popups", vars.corruption_popups, 1, 100))
        triggers_row.append(ConfigScale("Level Launches", vars.corruption_launches, 2, 31))

        reset_btn = Gtk.Button(label="Reset Launches")
        reset_btn.set_size_request(-1, 50)
        reset_btn.connect("clicked", lambda _: clear_launches(True))
        triggers_section.append(reset_btn)

        # Misc
        misc_section = ConfigSection("Misc. Settings")
        vbox.append(misc_section)

        misc_row = ConfigRow()
        misc_section.append(misc_row)
        misc_row.append(
            ConfigToggle("Don't Cycle Wallpaper", vars.corruption_wallpaper,
                tooltip="Prevents wallpaper from cycling during corruption.")
        )
        misc_row.append(
            ConfigToggle("Don't Cycle Themes", vars.corruption_themes,
                tooltip="Prevents themes from cycling during corruption.")
        )

        misc_row2 = ConfigRow()
        misc_section.append(misc_row2)
        misc_row2.append(
            ConfigToggle("Purity Mode", vars.corruption_purity,
                tooltip="Starts at highest corruption level, works backwards.")
        )
        misc_row2.append(
            ConfigToggle("Corruption Dev View", vars.corruption_dev_mode,
                tooltip="Shows debug info on popups.")
        )

        # Path
        if pack.corruption_levels:
            path_section = ConfigSection("Corruption Path", PATH_TEXT)
            vbox.append(path_section)

            columns = Gtk.ColumnView.new(Gtk.NoSelection.new(Gtk.StringList.new([])))
            for col_id, title in [("level", "LEVEL"), ("add", "ADD"), ("remove", "REMOVE"), ("wallpaper", "WALLPAPER"), ("config", "CONFIG")]:
                factory = Gtk.SignalListItemFactory()
                factory.connect("bind", lambda f, item, c=col_id: item.set_child(Gtk.Label(label="")))
                col = Gtk.ColumnViewColumn.new(title, factory)
                columns.append_column(col)

            path_section.append(columns)

    def _on_fade_changed(self, dropdown: Gtk.DropDown, _param) -> None:
        fade_types = ["Normal", "Abrupt"]
        selected = dropdown.get_selected()
        if 0 <= selected < len(fade_types):
            key = fade_types[selected]
            if key == "Normal":
                self._fade_desc.set_text("Gradually transitions between corruption levels.")
            else:
                self._fade_desc.set_text("Immediately switches to new level upon timer completion.")
