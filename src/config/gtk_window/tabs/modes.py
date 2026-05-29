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

from config.gtk_window.widgets import ConfigDropdown, ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.vars import Vars

LOWKEY_TEXT = "Forces popups to spawn in the corner of your screen."
HIBERNATE_TEXT = "Runs Edgeware++ covertly, without any popups. After a certain time, a barrage spawns."
MITOSIS_TEXT = "When a popup is closed, more popups will spawn in its place."


class BasicModesTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Lowkey
        lowkey_section = ConfigSection("Lowkey Mode", LOWKEY_TEXT)
        vbox.append(lowkey_section)

        lowkey_row = ConfigRow()
        lowkey_section.append(lowkey_row)
        lowkey_toggle = ConfigToggle("Enable Lowkey Mode", vars.lowkey_mode)
        lowkey_row.append(lowkey_toggle)

        lowkey_corners = ["Top Right", "Top Left", "Bottom Left", "Bottom Right", "Random"]
        strings = Gtk.StringList.new(lowkey_corners)
        corner_dropdown = Gtk.DropDown(model=strings)
        corner_value = vars.lowkey_corner.get()
        if isinstance(corner_value, int) and 0 <= corner_value < len(lowkey_corners):
            corner_dropdown.set_selected(corner_value)
        corner_dropdown.connect("notify::selected", lambda d, _: vars.lowkey_corner.set(d.get_selected()))
        lowkey_row.append(corner_dropdown)

        # Mitosis
        mitosis_section = ConfigSection("Mitosis Mode", MITOSIS_TEXT)
        vbox.append(mitosis_section)

        mr1 = ConfigRow()
        mitosis_section.append(mr1)
        mr1.append(ConfigToggle("Enable Mitosis Mode", vars.mitosis_mode))

        mr2 = ConfigRow()
        mitosis_section.append(mr2)
        mr2.append(ConfigScale("Mitosis Strength (number of popups)", vars.mitosis_strength, 2, 10))

        # Hibernate
        hib_section = ConfigSection("Hibernate Mode", HIBERNATE_TEXT)
        vbox.append(hib_section)

        hr1 = ConfigRow()
        hib_section.append(hr1)
        hr1.append(ConfigToggle("Enable Hibernate Mode", vars.hibernate_mode))

        hr2 = ConfigRow()
        hib_section.append(hr2)
        hr2.append(
            ConfigDropdown(
                vars.hibernate_type,
                {
                    "Original": "Creates an immediate quantity of popups on wakeup based on the awaken activity.",
                    "Spaced": "Creates popups consistently over the hibernate length, based on popup delay.",
                    "Glitch": "Creates popups at random times over the hibernate length.",
                    "Ramp": "Creates a ramping amount of popups over the hibernate length.",
                    "Pump-Scare": "Spawns a popup briefly, then quickly deletes it.",
                    "Chaos": "Every time hibernate activates, a random type is selected.",
                },
            )
        )

        hr3 = ConfigRow()
        hib_section.append(hr3)
        hr3.append(
            ConfigToggle("Fix Wallpaper", vars.hibernate_fix_wallpaper,
                tooltip="Reverts wallpaper back to panic wallpaper after hibernate payload.")
        )

        hr4 = ConfigRow()
        hib_section.append(hr4)
        hr4.append(ConfigScale("Minimum Sleep Duration (seconds)", vars.hibernate_delay_min, 1, 7200))
        hr4.append(ConfigScale("Maximum Sleep Duration (seconds)", vars.hibernate_delay_max, 2, 14400))

        hr5 = ConfigRow()
        hib_section.append(hr5)
        hr5.append(ConfigScale("Awaken Activity", vars.hibernate_activity, 1, 50))
        hr5.append(ConfigScale("Max Activity Length (seconds)", vars.hibernate_activity_length, 5, 300))
