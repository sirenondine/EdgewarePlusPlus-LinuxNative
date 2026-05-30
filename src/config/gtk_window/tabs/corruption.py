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
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.preset import apply_preset
from config.gtk_window.utils import clear_launches
from config.gtk_window.widgets import AdwComboRow, AdwSliderRow, AdwSwitchRow
from config.vars import Vars
from pack import Pack

INTRO_TEXT = (
    "Corruption is a highly specialised mode that packs must explicitly support. "
    "When enabled, moods are toggled on and off based on a trigger you configure here."
)
TRIGGER_TEXT = "Triggers define the goals that drive corruption progression over time."
PATH_TEXT = (
    "A summary of the corruption path the loaded pack will follow — levels, moods "
    "added/removed, wallpaper changes, and config overrides."
)

_TRIGGER_TYPES = {
    "Timed": "Transitions based on time elapsed.",
    "Popup": "Transitions based on number of popups shown.",
    "Launch": "Transitions based on number of Edgeware launches.",
    "Script": "Transitions handled by pack scripts.",
}

_FADE_TYPES = {
    "Normal": "Gradually transitions between corruption levels.",
    "Abrupt": "Immediately switches to a new level on trigger.",
}



class CorruptionModeTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars, pack: Pack) -> None:
        super().__init__()

        # ---- Enable / main controls -------------------------------------
        main = Adw.PreferencesGroup(title="Corruption Mode", description=INTRO_TEXT)
        self.add(main)

        has_corruption = os.path.isfile(pack.paths.corruption)
        enable_row = AdwSwitchRow(
            "Enable Corruption Mode", vars.corruption_mode,
            subtitle="Gradually makes the pack more depraved. Pack must support corruption.")
        enable_row.set_sensitive(has_corruption)
        main.add(enable_row)

        main.add(AdwSwitchRow(
            "Full Permissions Mode", vars.corruption_full,
            subtitle="Allows corruption to modify config settings."))

        if pack.config:
            rec_row = Adw.ActionRow(
                title="Recommended Settings",
                subtitle="Apply the pack creator's suggested corruption settings.",
            )
            rec_btn = Gtk.Button(label="Apply")
            rec_btn.set_valign(Gtk.Align.CENTER)
            rec_btn.connect("clicked", lambda _: apply_preset(
                pack.config, vars,
                ["corruptionMode", "corruptionTime", "corruptionFadeType"]))
            rec_row.add_suffix(rec_btn)
            rec_row.set_activatable_widget(rec_btn)
            main.add(rec_row)

        # ---- Triggers ----------------------------------------------------
        triggers = Adw.PreferencesGroup(title="Triggers", description=TRIGGER_TEXT)
        self.add(triggers)
        triggers.add(AdwComboRow("Trigger Type", vars.corruption_trigger, _TRIGGER_TYPES))
        triggers.add(AdwComboRow("Fade Type", vars.corruption_fade, _FADE_TYPES))
        triggers.add(AdwSliderRow("Level Time (seconds)", vars.corruption_time, 5, 1800))
        triggers.add(AdwSliderRow("Level Popups", vars.corruption_popups, 1, 100))
        triggers.add(AdwSliderRow("Level Launches", vars.corruption_launches, 2, 31))

        reset_row = Adw.ActionRow(
            title="Reset Launches",
            subtitle="Clear the launch counter used for the Launch trigger.",
        )
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.add_css_class("destructive-action")
        reset_btn.connect("clicked", lambda _: clear_launches(True))
        reset_row.add_suffix(reset_btn)
        reset_row.set_activatable_widget(reset_btn)
        triggers.add(reset_row)

        # ---- Misc settings -----------------------------------------------
        misc = Adw.PreferencesGroup(title="Misc. Settings")
        self.add(misc)
        misc.add(AdwSwitchRow(
            "Don't Cycle Wallpaper", vars.corruption_wallpaper,
            subtitle="Prevents wallpaper from cycling during corruption."))
        misc.add(AdwSwitchRow(
            "Don't Cycle Themes", vars.corruption_themes,
            subtitle="Prevents themes from cycling during corruption."))
        misc.add(AdwSwitchRow(
            "Purity Mode", vars.corruption_purity,
            subtitle="Starts at highest corruption level and works backwards."))
        misc.add(AdwSwitchRow(
            "Corruption Dev View", vars.corruption_dev_mode,
            subtitle="Shows debug information on popups."))

        # ---- Corruption path grid ----------------------------------------
        if pack.corruption_levels:
            path = Adw.PreferencesGroup(title="Corruption Path", description=PATH_TEXT)
            self.add(path)

            grid = Gtk.Grid()
            grid.set_column_spacing(16)
            grid.set_row_spacing(4)
            grid.set_margin_start(8)
            grid.set_margin_end(8)
            grid.set_margin_top(8)
            grid.set_margin_bottom(8)

            headers = ["Level", "Add Moods", "Remove Moods", "Wallpaper", "Config"]
            for col, title in enumerate(headers):
                lbl = Gtk.Label(label=title)
                lbl.add_css_class("heading")
                lbl.set_xalign(0)
                grid.attach(lbl, col, 0, 1, 1)

            grid.attach(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), 0, 1, len(headers), 1)

            for row_idx, level in enumerate(pack.corruption_levels):
                added = ", ".join(sorted(m for m in level.added_moods if m)) or "—"
                removed = ", ".join(sorted(m for m in level.removed_moods if m)) or "—"
                cfg = ", ".join(f"{k}={v}" for k, v in (level.config or {}).items()) or "—"
                for col, text in enumerate([str(row_idx), added, removed, level.wallpaper or "—", cfg]):
                    lbl = Gtk.Label(label=text)
                    lbl.set_xalign(0)
                    lbl.set_wrap(True)
                    grid.attach(lbl, col, row_idx + 2, 1, 1)

            scroller = Gtk.ScrolledWindow()
            scroller.set_min_content_height(160)
            scroller.set_child(grid)
            frame = Gtk.Frame()
            frame.add_css_class("card")
            frame.set_child(scroller)
            path.add(frame)
