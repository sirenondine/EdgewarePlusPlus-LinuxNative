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
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.preset import (
    apply_preset,
    list_presets,
    load_preset,
    load_preset_description,
    save_preset,
)
from config.gtk_window.utils import request_global_panic_key
from config.gtk_window.widgets import AdwSwitchRow
from config.vars import Vars
from pack import Pack

INTRO_TEXT = (
    "The Wayland-native build — GTK4 popups via layer-shell, GStreamer media, no "
    "Tkinter or X11. Use the tabs on the left to configure everything. Many buttons "
    "and sliders have tooltips. Set a panic hotkey below before you start."
)
PANIC_TEXT = (
    "\"Panic\" instantly halts Edgeware and reverts your desktop to the \"panic "
    "wallpaper\" set in the Wallpaper tab. On Wayland the global hotkey is registered "
    "through the desktop's GlobalShortcuts portal where supported; panic is also "
    "available from the tray icon and the panic command."
)
PRESET_TEXT = (
    "Be careful before importing unknown config presets! Double check the settings "
    "before launching Edgeware."
)


class StartTab(Adw.PreferencesPage):
    def __init__(
        self, vars: Vars, local_version: str, live_version: str, pack: Pack
    ) -> None:
        super().__init__()
        self._vars = vars

        # ---- Information -------------------------------------------------
        info = Adw.PreferencesGroup(title="Information", description=INTRO_TEXT)
        self.add(info)

        github_row = Adw.ActionRow(
            title="Edgeware++ LinuxNative",
            subtitle="Open the project page on GitHub.",
        )
        github_btn = Gtk.Button(label="Open GitHub")
        github_btn.set_valign(Gtk.Align.CENTER)
        github_btn.connect("clicked", lambda _: webbrowser.open(
            "https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative"))
        github_row.add_suffix(github_btn)
        github_row.set_activatable_widget(github_btn)
        info.add(github_row)

        download_row = Adw.ActionRow(
            title="Newest Update",
            subtitle="Download the latest source archive.",
        )
        download_btn = Gtk.Button(label="Download")
        download_btn.set_valign(Gtk.Align.CENTER)
        download_btn.connect("clicked", lambda _: webbrowser.open(
            "https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative/archive/refs/heads/main.zip"))
        download_row.add_suffix(download_btn)
        download_row.set_activatable_widget(download_btn)
        info.add(download_row)

        local_row = Adw.ActionRow(title="Installed Version")
        local_row.add_suffix(_value_label(local_version))
        info.add(local_row)

        github_ver_row = Adw.ActionRow(title="Latest on GitHub")
        mismatch = bool(live_version) and local_version != live_version
        github_ver_row.add_suffix(_value_label(
            live_version or "unknown", mismatch=mismatch))
        info.add(github_ver_row)

        # ---- Pack configuration ------------------------------------------
        pack_group = Adw.PreferencesGroup(
            title="Pack Configuration",
            description=(
                "Pack creators can ship a config file with settings tailored to their "
                "intended experience."
            ),
        )
        self.add(pack_group)

        load_pack_row = Adw.ActionRow(
            title="Load Pack Configuration",
            subtitle=f"{len(pack.config)} suggested settings in this pack.",
        )
        load_pack_btn = Gtk.Button(label="Load")
        load_pack_btn.set_valign(Gtk.Align.CENTER)
        load_pack_btn.set_sensitive(bool(pack.config))
        load_pack_btn.connect("clicked", lambda _: apply_preset(pack.config, vars))
        load_pack_row.add_suffix(load_pack_btn)
        load_pack_row.set_activatable_widget(load_pack_btn)
        pack_group.add(load_pack_row)

        pack_group.add(AdwSwitchRow(
            "Force Warning Failsafes", vars.preset_danger,
            subtitle=(
                "Turns on \"Warn if Dangerous Settings Active\" after loading a pack "
                "config, regardless of the config's own setting."
            )))

        # ---- Panic -------------------------------------------------------
        panic_group = Adw.PreferencesGroup(title="Panic Settings", description=PANIC_TEXT)
        self.add(panic_group)

        panic_key_row = Adw.ActionRow(
            title="Global Panic Key",
            subtitle=(
                "Works without focus. Compositors using the GlobalShortcuts portal "
                "(KDE/GNOME) may let you rebind it in system settings; otherwise "
                "Edgeware falls back to evdev (requires the 'input' group)."
            ),
        )
        self.global_panic_btn = Gtk.Button(label=f"<{vars.global_panic_key.get()}>")
        self.global_panic_btn.set_valign(Gtk.Align.CENTER)
        self.global_panic_btn.connect(
            "clicked",
            lambda _: request_global_panic_key(self.global_panic_btn, vars.global_panic_key),
        )
        panic_key_row.add_suffix(self.global_panic_btn)
        panic_key_row.set_activatable_widget(self.global_panic_btn)
        panic_group.add(panic_key_row)

        panic_now_row = Adw.ActionRow(
            title="Perform Panic",
            subtitle="Stop Edgeware now and revert your wallpaper.",
        )
        panic_btn = Gtk.Button(label="Panic")
        panic_btn.set_valign(Gtk.Align.CENTER)
        panic_btn.add_css_class("destructive-action")
        panic_btn.connect("clicked", self._on_perform_panic)
        panic_now_row.add_suffix(panic_btn)
        panic_now_row.set_activatable_widget(panic_btn)
        panic_group.add(panic_now_row)

        # ---- General settings --------------------------------------------
        general = Adw.PreferencesGroup(title="General Settings")
        self.add(general)
        general.add(AdwSwitchRow(
            "Show Loading Flair", vars.startup_splash,
            subtitle="Displays a brief \"loading\" image before Edgeware startup."))
        general.add(AdwSwitchRow("Run Edgeware on Save &amp; Exit", vars.run_on_save_quit))
        general.add(AdwSwitchRow("Create Desktop Icons", vars.desktop_icons))
        general.add(AdwSwitchRow(
            "Warn if \"Dangerous\" Settings Active", vars.safe_mode,
            subtitle="Asks you to confirm before saving if certain settings are enabled."))
        general.add(AdwSwitchRow("Disable Config Help Messages", vars.message_off))

        # ---- Config presets ----------------------------------------------
        preset_group = Adw.PreferencesGroup(title="Config Presets", description=PRESET_TEXT)
        self.add(preset_group)

        preset_list = list_presets()
        self._presets_found = bool(preset_list)

        self._preset_row = Adw.ComboRow(title="Preset")
        self._preset_row.set_model(Gtk.StringList.new(
            preset_list if preset_list else ["No presets found"]))
        self._preset_row.set_sensitive(self._presets_found)
        self._preset_row.connect("notify::selected", self._on_preset_selected)
        preset_group.add(self._preset_row)

        self._preset_desc_row = Adw.ActionRow(title="Description")
        self._preset_desc_row.set_subtitle(
            load_preset_description(preset_list[0]) if self._presets_found else "")
        preset_group.add(self._preset_desc_row)

        load_preset_row = Adw.ActionRow(
            title="Load Preset",
            subtitle="Apply the selected preset's settings.",
        )
        self.load_preset_btn = Gtk.Button(label="Load")
        self.load_preset_btn.set_valign(Gtk.Align.CENTER)
        self.load_preset_btn.set_sensitive(self._presets_found)
        self.load_preset_btn.connect("clicked", self._on_load_preset)
        load_preset_row.add_suffix(self.load_preset_btn)
        load_preset_row.set_activatable_widget(self.load_preset_btn)
        preset_group.add(load_preset_row)

        save_preset_row = Adw.ActionRow(
            title="Save Preset",
            subtitle="Store the current settings as a new preset.",
        )
        save_preset_btn = Gtk.Button(label="Save")
        save_preset_btn.set_valign(Gtk.Align.CENTER)
        save_preset_btn.connect("clicked", lambda _: save_preset())
        save_preset_row.add_suffix(save_preset_btn)
        save_preset_row.set_activatable_widget(save_preset_btn)
        preset_group.add(save_preset_row)

    def _on_perform_panic(self, btn: Gtk.Button) -> None:
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.append(Gtk.Label(label="Stop Edgeware and revert wallpaper?"))
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        confirm_btn = Gtk.Button(label="Panic")
        confirm_btn.add_css_class("destructive-action")
        confirm_btn.connect("clicked", lambda _: (popover.popdown(), self._perform_panic()))
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: popover.popdown())
        btn_row.append(confirm_btn)
        btn_row.append(cancel_btn)
        vbox.append(btn_row)
        popover.set_child(vbox)
        popover.set_parent(btn)
        popover.popup()

    @staticmethod
    def _perform_panic() -> None:
        from panic import send_panic
        send_panic()

    def _on_preset_selected(self, row: Adw.ComboRow, _param) -> None:
        if not self._presets_found:
            return
        model = row.get_model()
        name = model.get_string(row.get_selected())
        self._update_preset_description(name)

    def _update_preset_description(self, name: str) -> None:
        self._preset_desc_row.set_subtitle(load_preset_description(name))

    def _on_load_preset(self, _btn: Gtk.Button) -> None:
        model = self._preset_row.get_model()
        name = model.get_string(self._preset_row.get_selected())
        apply_preset(load_preset(name), self._vars)


def _value_label(text: str, mismatch: bool = False) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.add_css_class("dim-label" if not mismatch else "version-mismatch")
    return lbl
