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
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.widgets import AdwComboRow, AdwSliderRow, AdwSwitchRow
from config.vars import Vars

LOWKEY_TEXT = "Forces popups to spawn in one corner of your screen."
HIBERNATE_TEXT = "Runs Edgeware covertly with no popups. After a set time, a barrage of popups spawns."
MITOSIS_TEXT = "When a popup is closed, more popups spawn in its place."

_HIBERNATE_TYPES = {
    "Original": "An immediate quantity of popups on wakeup based on Awaken Activity.",
    "Spaced": "Popups appear consistently over the hibernate length, based on popup delay.",
    "Glitch": "Popups appear at random times over the hibernate length.",
    "Ramp": "A ramping number of popups over the hibernate length.",
    "Pump-Scare": "A popup spawns briefly then disappears.",
    "Chaos": "A random type is selected each time hibernate activates.",
}

_LOWKEY_CORNERS = ["Top Right", "Top Left", "Bottom Left", "Bottom Right", "Random"]


class BasicModesTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        # ---- Lowkey ------------------------------------------------------
        lowkey = Adw.PreferencesGroup(title="Lowkey Mode", description=LOWKEY_TEXT)
        self.add(lowkey)
        lowkey.add(AdwSwitchRow("Enable Lowkey Mode", vars.lowkey_mode))

        corner_row = Adw.ComboRow(title="Corner")
        corner_row.set_model(Gtk.StringList.new(_LOWKEY_CORNERS))
        val = vars.lowkey_corner.get()
        if isinstance(val, int) and 0 <= val < len(_LOWKEY_CORNERS):
            corner_row.set_selected(val)
        corner_row.connect("notify::selected", lambda r, _p: vars.lowkey_corner.set(r.get_selected()))
        lowkey.add(corner_row)

        # ---- Mitosis -----------------------------------------------------
        mitosis = Adw.PreferencesGroup(title="Mitosis Mode", description=MITOSIS_TEXT)
        self.add(mitosis)
        mitosis.add(AdwSwitchRow("Enable Mitosis Mode", vars.mitosis_mode))
        mitosis.add(AdwSliderRow("Mitosis Strength", vars.mitosis_strength, 2, 10,
                                  subtitle="Number of popups spawned per close"))

        # ---- Hibernate ---------------------------------------------------
        hibernate = Adw.PreferencesGroup(title="Hibernate Mode", description=HIBERNATE_TEXT)
        self.add(hibernate)
        hibernate.add(AdwSwitchRow("Enable Hibernate Mode", vars.hibernate_mode))
        hibernate.add(AdwComboRow("Hibernate Type", vars.hibernate_type, _HIBERNATE_TYPES))
        hibernate.add(AdwSwitchRow(
            "Fix Wallpaper", vars.hibernate_fix_wallpaper,
            subtitle="Reverts wallpaper to panic wallpaper after the hibernate payload."))
        hibernate.add(AdwSliderRow("Minimum Sleep Duration (sec)", vars.hibernate_delay_min, 1, 7200))
        hibernate.add(AdwSliderRow("Maximum Sleep Duration (sec)", vars.hibernate_delay_max, 2, 14400))
        hibernate.add(AdwSliderRow("Awaken Activity", vars.hibernate_activity, 1, 50))
        hibernate.add(AdwSliderRow("Max Activity Length (sec)", vars.hibernate_activity_length, 5, 300))
