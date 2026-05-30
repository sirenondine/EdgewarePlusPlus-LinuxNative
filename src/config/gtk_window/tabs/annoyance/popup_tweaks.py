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
from gi.repository import Adw

from config.gtk_window.widgets import AdwSliderRow, AdwSwitchRow
from config.gtk_window.utils import config
from config.vars import Vars
from screeninfo import get_monitors

OVERLAY_TEXT = (
    "Modifiers applied on top of popups. Hypno overlays a transparent gif; "
    "Denial \"censors\" a popup by blurring it."
)
CAPTION_TEXT = "Small bits of text that adorn each popup."
MONITORS_TEXT = "Choose which monitors Edgeware++ may spawn popups on."
MOVEMENT_TEXT = "Give each popup a chance to drift around the screen."
TIMEOUT_TEXT = "After a set time, popups fade out and delete themselves."


def _monitor_row(monitor) -> Adw.SwitchRow:
    """A switch row that enables/disables popups on one monitor (writes the
    disabledMonitors config list directly, not a ConfigVar)."""
    row = Adw.SwitchRow(title=monitor.name, subtitle=f"{monitor.width}×{monitor.height}")
    row.set_active(monitor.name not in config.get("disabledMonitors", []))

    def on_toggled(r, _p):
        disabled = config.setdefault("disabledMonitors", [])
        if r.get_active():
            if monitor.name in disabled:
                disabled.remove(monitor.name)
        elif monitor.name not in disabled:
            disabled.append(monitor.name)

    row.connect("notify::active", on_toggled)
    return row


class PopupTweaksTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        captions = Adw.PreferencesGroup(title="Captions", description=CAPTION_TEXT)
        self.add(captions)
        captions.add(AdwSwitchRow("Enable Popup Captions", vars.captions_in_popups))

        overlays = Adw.PreferencesGroup(title="Overlays", description=OVERLAY_TEXT)
        self.add(overlays)
        overlays.add(AdwSliderRow("Hypno Chance (%)", vars.hypno_chance, 0, 100))
        overlays.add(AdwSliderRow("Hypno Opacity (%)", vars.hypno_opacity, 1, 99))
        overlays.add(AdwSliderRow("Denial Chance (%)", vars.denial_chance, 0, 100))

        opacity = Adw.PreferencesGroup(title="Opacity")
        self.add(opacity)
        opacity.add(AdwSliderRow("Popup Opacity (%)", vars.opacity, 5, 100))

        timeout = Adw.PreferencesGroup(title="Popup Timeout", description=TIMEOUT_TEXT)
        self.add(timeout)
        timeout.add(AdwSwitchRow("Enable Popup Timeout", vars.timeout_enabled))
        timeout.add(AdwSliderRow("Timeout (seconds)", vars.timeout, 1, 120))

        misc = Adw.PreferencesGroup(title="Misc. Tweaks")
        self.add(misc)
        misc.add(AdwSwitchRow(
            "Buttonless Closing Popups", vars.buttonless,
            subtitle="Removes the close button; click a popup anywhere to close it."))
        misc.add(AdwSwitchRow(
            "Multi-Click Popups", vars.multi_click_popups,
            subtitle="Popups take several clicks to close."))

        monitors = Adw.PreferencesGroup(title="Monitors", description=MONITORS_TEXT)
        self.add(monitors)
        monitors.add(AdwSwitchRow(
            "Spawn on Active Monitor", vars.spawn_on_active_monitor,
            subtitle="Put popups on the monitor you're focused on (niri only)."))
        for monitor in get_monitors():
            monitors.add(_monitor_row(monitor))

        movement = Adw.PreferencesGroup(title="Popup Movement", description=MOVEMENT_TEXT)
        self.add(movement)
        movement.add(AdwSliderRow("Moving Popup Chance (%)", vars.moving_chance, 0, 100))
        movement.add(AdwSliderRow("Max Move Speed", vars.moving_speed, 1, 15))
