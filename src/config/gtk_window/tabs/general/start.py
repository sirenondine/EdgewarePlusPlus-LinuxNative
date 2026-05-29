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

import webbrowser

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.gtk_window.preset import (
    apply_preset,
    list_presets,
    load_preset,
    load_preset_description,
    save_preset,
)
from config.gtk_window.utils import (
    request_global_panic_key,
)
from config.gtk_window.widgets import (
    PAD,
    ConfigRow,
    ConfigSection,
    ConfigToggle,
)
from config.vars import Vars
from pack import Pack
from paths import CustomAssets

INTRO_TEXT = (
    "Welcome to Edgeware++!\n"
    "You can use the tabs at the top of this window to navigate the various config settings "
    "for the main program. Annoyance/Runtime is for how the program works while running, "
    "Modes is for more complicated and involved settings that change how Edgeware works drastically, "
    "and Troubleshooting and About are for learning this program better and fixing errors should "
    "anything go wrong.\n\n"
    "Aside from these helper memos, there are also tooltips on several buttons and sliders. "
    "If you see your mouse cursor change to a \"question mark\", hover for a second or two to "
    "see more information on the setting."
)
PANIC_TEXT = (
    "\"Panic\" is a feature that allows you to instantly halt the program and revert your "
    "desktop background back to the \"panic background\" set in the wallpaper sub-tab. "
    "(found in the annoyance tab)\n\n"
    "There are a few ways to initiate panic, but one of the easiest to access is setting a "
    "hotkey here. You should also make sure to change your panic wallpaper to your currently "
    "used wallpaper before using Edgeware!"
)
PRESET_TEXT = (
    "Please be careful before importing unknown config presets! Double check to make sure "
    "you're okay with the settings before launching Edgeware."
)


class StartTab(Gtk.ScrolledWindow):
    def __init__(
        self, vars: Vars, local_version: str, live_version: str, pack: Pack
    ) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._vars = vars

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        vbox.set_margin_start(PAD * 2)
        vbox.set_margin_end(PAD * 2)
        vbox.set_margin_top(PAD * 2)
        vbox.set_margin_bottom(PAD * 2)
        self.set_child(vbox)

        # Information
        info_section = ConfigSection("Information", INTRO_TEXT)
        vbox.append(info_section)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        info_section.append(btn_box)

        col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        btn_box.append(col1)

        github_btn = Gtk.Button(label="Open Edgeware++ Github")
        github_btn.connect("clicked", lambda _: webbrowser.open("https://github.com/araten10/EdgewarePlusPlus"))
        col1.append(github_btn)

        download_btn = Gtk.Button(label="Download Newest Update")
        download_btn.connect(
            "clicked",
            lambda _: webbrowser.open(
                "https://github.com/araten10/EdgewarePlusPlus/archive/refs/heads/main.zip"
            ),
        )
        col1.append(download_btn)

        col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        btn_box.append(col2)

        local_lbl = Gtk.Label(label=f"Edgeware++ Local Version:\n{local_version}")
        local_lbl.set_xalign(0)
        col2.append(local_lbl)

        github_lbl = Gtk.Label(label=f"Edgeware++ Github Version:\n{live_version}")
        github_lbl.set_xalign(0)
        if local_version != live_version:
            github_lbl.add_css_class("version-mismatch")
        col2.append(github_lbl)

        # Pack preset
        pack_section = Gtk.Frame(css_classes=["config-section"])
        pack_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        pack_section.set_child(pack_vbox)
        vbox.append(pack_section)

        pack_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        pack_vbox.append(pack_row)

        pack_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        pack_row.append(pack_col1)

        config_count_lbl = Gtk.Label(
            label=f"Number of suggested config settings: {len(pack.config)}"
        )
        config_count_lbl.set_xalign(0)
        pack_col1.append(config_count_lbl)

        danger_toggle = ConfigToggle(
            "Toggle on warning failsafes", vars.preset_danger,
            tooltip=(
                "Toggles on the \"Warn if \"Dangerous\" Settings Active\" setting after loading the "
                "pack configuration file, regardless if it was toggled on or off in those settings."
            ),
        )
        pack_col1.append(danger_toggle)

        pack_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        pack_row.append(pack_col2)

        load_pack_btn = Gtk.Button(label="Load Pack Configuration")
        load_pack_btn.set_tooltip_text(
            "In Edgeware++, the functionality was added for pack creators to add a config file "
            "to their pack, allowing for quick loading of setting presets tailored to their intended "
            "pack experience."
        )
        load_pack_btn.connect("clicked", lambda _: apply_preset(pack.config, vars))
        pack_col2.append(load_pack_btn)

        if not pack.config:
            load_pack_btn.set_sensitive(False)

        # Panic
        panic_section = ConfigSection("Panic Settings", PANIC_TEXT)
        vbox.append(panic_section)

        panic_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        panic_section.append(panic_row)

        self.global_panic_btn = Gtk.Button(
            label=f"Set Global\nPanic Key\n<{vars.global_panic_key.get()}>"
        )
        self.global_panic_btn.set_tooltip_text(
            "This is a global key that does not require focus to activate."
        )
        self.global_panic_btn.connect(
            "clicked",
            lambda _: request_global_panic_key(self.global_panic_btn, vars.global_panic_key),
        )
        panic_row.append(self.global_panic_btn)

        panic_btn = Gtk.Button(label="Perform Panic")
        panic_btn.connect("clicked", lambda _: self._perform_panic())
        panic_row.append(panic_btn)

        # Other settings
        other_section = ConfigSection("General Settings")
        vbox.append(other_section)

        other_row = ConfigRow()
        other_section.append(other_row)

        toggle_flair = ConfigToggle(
            "Show Loading Flair", vars.startup_splash,
            tooltip="Displays a brief \"loading\" image before Edgeware startup.",
        )
        other_row.append(toggle_flair)
        other_row.append(ConfigToggle("Run Edgeware on Save & Exit", vars.run_on_save_quit))
        other_row_2 = ConfigRow()
        other_section.append(other_row_2)
        other_row_2.append(ConfigToggle("Create Desktop Icons", vars.desktop_icons))
        toggle_safe = ConfigToggle(
            'Warn if "Dangerous" Settings Active', vars.safe_mode,
            tooltip="Asks you to confirm before saving if certain settings are enabled.",
        )
        other_row_2.append(toggle_safe)
        other_row_3 = ConfigRow()
        other_section.append(other_row_3)
        other_row_3.append(ConfigToggle("Disable Config Help Messages", vars.message_off))

        # Presets
        preset_section = ConfigSection("Config Presets", PRESET_TEXT)
        vbox.append(preset_section)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        preset_section.append(preset_row)

        preset_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        preset_row.append(preset_col)

        preset_list = list_presets()
        self._presets_found = bool(preset_list)

        preset_strings = Gtk.StringList.new(preset_list if preset_list else ["No presets found"])
        self.preset_dropdown = Gtk.DropDown(model=preset_strings)
        preset_col.append(self.preset_dropdown)
        self.preset_dropdown.connect("notify::selected", self._on_preset_selected)

        self.load_preset_btn = Gtk.Button(label="Load Preset")
        self.load_preset_btn.set_sensitive(self._presets_found)
        self.load_preset_btn.connect("clicked", self._on_load_preset)
        preset_col.append(self.load_preset_btn)

        save_preset_btn = Gtk.Button(label="Save Preset")
        save_preset_btn.connect("clicked", lambda _: save_preset())
        preset_col.append(save_preset_btn)

        self._preset_desc_frame = Gtk.Frame(css_classes=["preset-description"])
        preset_row.append(self._preset_desc_frame)

        self._preset_desc_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAD)
        self._preset_desc_frame.set_child(self._preset_desc_vbox)

        self._preset_name_lbl = Gtk.Label(
            label="No presets found" if not self._presets_found else preset_list[0],
            wrap=True,
        )
        self._preset_name_lbl.set_xalign(0)
        self._preset_name_lbl.add_css_class("heading")
        self._preset_desc_vbox.append(self._preset_name_lbl)

        self._preset_desc_lbl = Gtk.Label(label="")
        self._preset_desc_lbl.set_xalign(0)
        self._preset_desc_lbl.set_wrap(True)
        self._preset_desc_vbox.append(self._preset_desc_lbl)

        if self._presets_found:
            self._update_preset_description(preset_list[0])

    @staticmethod
    def _perform_panic() -> None:
        from panic import send_panic
        send_panic()

    def _on_preset_selected(self, dropdown: Gtk.DropDown, _param) -> None:
        if not self._presets_found:
            return
        from config.gtk_window.preset import load_preset_description
        model = dropdown.get_model()
        name = model.get_string(dropdown.get_selected())
        self._update_preset_description(name)

    def _update_preset_description(self, name: str) -> None:
        self._preset_name_lbl.set_text(f"{name} Description")
        self._preset_desc_lbl.set_text(load_preset_description(name))

    def _on_load_preset(self, _btn: Gtk.Button) -> None:
        from config.gtk_window.preset import apply_preset, load_preset
        selected = self.preset_dropdown.get_selected()
        model = self.preset_dropdown.get_model()
        name = model.get_string(selected)
        apply_preset(load_preset(name), self._vars)


