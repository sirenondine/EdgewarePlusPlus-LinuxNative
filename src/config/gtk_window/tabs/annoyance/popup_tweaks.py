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

import os_utils
from config.gtk_window.widgets import ConfigMessage, ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.gtk_window.utils import config
from config.vars import Vars
from screeninfo import get_monitors

OVERLAY_TEXT = (
    "Overlays are modifiers for popups.\n"
    "Hypno adds a transparent gif over affected popups.\n"
    "Denial \"censors\" a popup by blurring it."
)
CAPTION_TEXT = "Captions are small bits of text that adorn each popup."
MONITORS_TEXT = "Choose what monitors Edgeware++ will spawn popups on!"
MOVEMENT_TEXT = "Gives each popup a chance to move around the screen."
MISC_TEXT = (
    "\"Buttonless Closing Popups\" removes the close button on every popup.\n"
    "\"Multi Click Popups\" makes popups take more clicks to close.\n"
    "\"Popup Opacity\" affects the transparency of all popups."
)
TIMEOUT_TEXT = "After a certain time, popups will fade out and delete themselves."
CLICKTHROUGH_TEXT = (
    "When turned on, all popups will have their buttons removed, and you will be unable to click on them."
)


class MonitorToggle(Gtk.Box):
    def __init__(self, monitor) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._monitor = monitor
        disabled = config.get("disabledMonitors", [])
        is_active = monitor.name not in disabled

        switch = Gtk.Switch()
        switch.set_active(is_active)
        switch.connect("notify::active", self._on_toggled)
        self.append(switch)

        lbl = Gtk.Label(label=f"{monitor.name} ({monitor.width}x{monitor.height})")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        self.append(lbl)

    def _on_toggled(self, switch: Gtk.Switch, _param) -> None:
        disabled = config.get("disabledMonitors", [])
        if switch.get_active():
            if self._monitor.name in disabled:
                disabled.remove(self._monitor.name)
        else:
            if self._monitor.name not in disabled:
                disabled.append(self._monitor.name)


class PopupTweaksTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Captions
        caps_section = ConfigSection("Captions", CAPTION_TEXT)
        vbox.append(caps_section)
        caps_section.append(ConfigToggle("Enable Popup Captions", vars.captions_in_popups))

        # Overlays
        ov_section = ConfigSection("Overlays", OVERLAY_TEXT)
        vbox.append(ov_section)
        hypno_row = ConfigRow()
        ov_section.append(hypno_row)
        hypno_row.append(ConfigScale("Hypno Chance (%)", vars.hypno_chance, 0, 100))
        hypno_row.append(ConfigScale("Hypno Opacity (%)", vars.hypno_opacity, 1, 99))
        denial_row = ConfigRow()
        ov_section.append(denial_row)
        denial_row.append(ConfigScale("Denial Chance (%)", vars.denial_chance, 0, 100))

        # Opacity
        opacity_section = ConfigSection("Opacity")
        vbox.append(opacity_section)
        op_row = ConfigRow()
        opacity_section.append(op_row)
        op_row.append(ConfigScale("Popup Opacity (%)", vars.opacity, 5, 100))
        opacity_section.append(ConfigMessage(CLICKTHROUGH_TEXT))

        ct_row = ConfigRow()
        opacity_section.append(ct_row)
        ct_toggle = ConfigToggle("Clickthrough Popups (Windows Only)", vars.clickthrough_enabled)
        ct_toggle.set_sensitive(os_utils.is_windows())
        ct_row.append(ct_toggle)

        # Timeout
        timeout_section = ConfigSection("Popup Timeout", TIMEOUT_TEXT)
        vbox.append(timeout_section)
        t_row = ConfigRow()
        timeout_section.append(t_row)
        t_row.append(ConfigToggle("Popup Timeout", vars.timeout_enabled))
        t_row_2 = ConfigRow()
        timeout_section.append(t_row_2)
        t_row_2.append(ConfigScale("Time (sec)", vars.timeout, 1, 120))

        # Misc
        misc_section = ConfigSection("Misc. Tweaks", MISC_TEXT)
        vbox.append(misc_section)
        m_row = ConfigRow()
        misc_section.append(m_row)
        m_row.append(
            ConfigToggle("Buttonless Closing Popups", vars.buttonless,
                tooltip="Panic hotkey only works while holding mouse over a popup!")
        )
        m_row.append(ConfigToggle("Multi-Click popups", vars.multi_click_popups))

        # Monitors
        monitors_section = ConfigSection("Monitors", MONITORS_TEXT)
        vbox.append(monitors_section)
        for monitor in get_monitors():
            monitors_section.append(MonitorToggle(monitor))

        # Movement
        move_section = ConfigSection("Popup Movement", MOVEMENT_TEXT)
        vbox.append(move_section)
        mv_row = ConfigRow()
        move_section.append(mv_row)
        mv_row.append(ConfigScale("Moving Popup Chance", vars.moving_chance, 0, 100))
        mv_row.append(ConfigScale("Max Movespeed", vars.moving_speed, 1, 15))
