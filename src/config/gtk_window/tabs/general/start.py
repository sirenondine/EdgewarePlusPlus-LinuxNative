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
import re
from pathlib import Path

import os_utils

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.preset import (
    apply_preset,
    compute_preset_diff,
    delete_preset,
    list_presets,
    load_preset,
    load_preset_description,
    save_preset,
)
from config.gtk_window.utils import pretty_panic_key, request_global_panic_key
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

# Niri doesn't support the GlobalShortcuts portal, so the panic hotkey falls
# back to evdev (needs the 'input' group) — usually unavailable. Guide users
# to add a native niri keybind that calls edgeware panic over the socket.
_EDGEWARE_DIR = Path(__file__).resolve().parents[5]  # repo root
_NIRI_CONFIG = Path.home() / ".config" / "niri" / "config.kdl"


def _is_niri() -> bool:
    return bool(os.environ.get("NIRI_SOCKET"))


def _niri_keybind_snippet(key_label: str) -> str:
    edgeware = _EDGEWARE_DIR / "edgeware"
    return (
        f'// Add to ~/.config/niri/config.kdl:\n'
        f'binds {{\n'
        f'    {key_label} {{ spawn "{edgeware}" "panic"; }}\n'
        f'}}'
    )


def _search_niri_kdls(pattern: str) -> bool:
    """Return True if `pattern` matches any text in any .kdl under ~/.config/niri/."""
    niri_dir = _NIRI_CONFIG.parent
    if not niri_dir.is_dir():
        return False
    for kdl in niri_dir.rglob("*.kdl"):
        try:
            if re.search(pattern, kdl.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            pass
    return False


def _niri_keybind_configured() -> bool:
    return _search_niri_kdls(r'"[^"]*edgeware[^"]*"\s+"panic"')


def _niri_append_config(path: Path, snippet: str) -> "str | None":
    lines = snippet.splitlines()
    body = "\n".join(lines[1:] if lines and lines[0].startswith("//") else lines)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        sep = "\n\n" if path.is_file() and path.stat().st_size > 0 else ""
        with path.open("a", encoding="utf-8") as f:
            f.write(sep + body + "\n")
        return None
    except OSError as e:
        return str(e)


def _niri_keybind_row(key_var) -> Adw.ActionRow:
    from config.gtk_window.utils import pretty_panic_key

    key_label = pretty_panic_key(key_var.get())
    snippet = _niri_keybind_snippet(key_label)
    already = _niri_keybind_configured()

    row = Adw.ActionRow()
    row.set_activatable(False)

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    vbox.set_margin_start(12)
    vbox.set_margin_end(12)
    vbox.set_margin_top(10)
    vbox.set_margin_bottom(10)

    # Status stack: warning (not configured) vs success (verified)
    warn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    warn_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
    warn_icon.add_css_class("warning")
    warn_icon.set_valign(Gtk.Align.START)
    warn_lbl = Gtk.Label(wrap=True, xalign=0, hexpand=True)
    warn_lbl.set_text(
        "Niri doesn't implement the GlobalShortcuts portal, so the global panic "
        "hotkey above won't fire. Add a native niri keybind that calls edgeware panic "
        "directly over the Unix socket — it always works regardless of portal support:"
    )
    warn_box.append(warn_icon)
    warn_box.append(warn_lbl)

    ok_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
    ok_icon.add_css_class("success")
    ok_icon.set_valign(Gtk.Align.CENTER)
    ok_lbl = Gtk.Label(wrap=True, xalign=0, hexpand=True)
    ok_lbl.set_text("config.kdl is configured with an edgeware panic keybind.")
    ok_box.append(ok_icon)
    ok_box.append(ok_lbl)

    status_stack = Gtk.Stack()
    status_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    status_stack.add_named(warn_box, "warn")
    status_stack.add_named(ok_box, "ok")
    status_stack.set_visible_child_name("ok" if already else "warn")
    vbox.append(status_stack)

    # Monospaced snippet + hint + buttons — hidden when already configured
    code_view = Gtk.TextView()
    code_view.set_editable(False)
    code_view.set_monospace(True)
    code_view.set_wrap_mode(Gtk.WrapMode.NONE)
    code_view.set_cursor_visible(False)
    code_view.add_css_class("card")
    code_view.get_buffer().set_text(snippet)
    code_view.set_visible(not already)
    vbox.append(code_view)

    hint = Gtk.Label(
        label="~/.config/niri/config.kdl — reload with: niri msg action reload-config",
        xalign=0, wrap=True,
    )
    hint.add_css_class("dim-label")
    hint.set_visible(not already)
    vbox.append(hint)

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_box.set_halign(Gtk.Align.END)
    btn_box.set_visible(not already)

    add_btn = Gtk.Button(label="Add to config.kdl")
    add_btn.add_css_class("suggested-action")

    copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
    copy_btn.set_tooltip_text("Copy niri keybind to clipboard")

    btn_box.append(add_btn)
    btn_box.append(copy_btn)
    vbox.append(btn_box)

    def _set_configured():
        status_stack.set_visible_child_name("ok")
        code_view.set_visible(False)
        hint.set_visible(False)
        btn_box.set_visible(False)

    def on_add(_b):
        from config.gtk_window.toast import toast
        err = _niri_append_config(_NIRI_CONFIG, snippet)
        if err:
            toast(f"Failed: {err}")
        else:
            _set_configured()
            toast("Added to config.kdl — reload: niri msg action reload-config")

    def on_copy(_b):
        clipboard = copy_btn.get_clipboard()
        if clipboard:
            clipboard.set(snippet)
        from config.gtk_window.toast import toast
        toast("Keybind config copied")

    add_btn.connect("clicked", on_add)
    copy_btn.connect("clicked", on_copy)

    row.set_child(vbox)
    return row


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
        github_btn = Gtk.Button()
        github_btn.set_child(Adw.ButtonContent(label="Open GitHub", icon_name="web-browser-symbolic"))
        github_btn.set_valign(Gtk.Align.CENTER)
        github_btn.connect("clicked", lambda _: os_utils.open_url(
            "https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative"))
        github_row.add_suffix(github_btn)
        github_row.set_activatable_widget(github_btn)
        info.add(github_row)

        download_row = Adw.ActionRow(
            title="Newest Update",
            subtitle="Download the latest source archive.",
        )
        download_btn = Gtk.Button()
        download_btn.set_child(Adw.ButtonContent(label="Download", icon_name="folder-download-symbolic"))
        download_btn.set_valign(Gtk.Align.CENTER)
        download_btn.connect("clicked", lambda _: os_utils.open_url(
            "https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative/archive/refs/heads/main.zip"))
        download_row.add_suffix(download_btn)
        download_row.set_activatable_widget(download_btn)
        info.add(download_row)
        # Version rows live on the Home dashboard now.

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
        self.global_panic_btn = Gtk.Button(label=f"<{pretty_panic_key(vars.global_panic_key.get())}>")
        self.global_panic_btn.set_valign(Gtk.Align.CENTER)
        self.global_panic_btn.connect(
            "clicked",
            lambda _: request_global_panic_key(self.global_panic_btn, vars.global_panic_key),
        )
        panic_key_row.add_suffix(self.global_panic_btn)
        panic_key_row.set_activatable_widget(self.global_panic_btn)
        panic_group.add(panic_key_row)

        if _is_niri():
            panic_group.add(_niri_keybind_row(vars.global_panic_key))

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
        general.add(AdwSwitchRow(
            "Open Dashboard on Launch", vars.dashboard_on_launch,
            subtitle="Running \"edgeware\" opens the Home dashboard instead of starting "
                     "immediately. Use \"edgeware run\" to skip it."))
        general.add(AdwSwitchRow("Create Desktop Icons", vars.desktop_icons))
        general.add(AdwSwitchRow(
            "Pause When Screen Locks", vars.pause_on_lock,
            subtitle="Pauses popups while locked (via logind / ScreenSaver). Lockers "
                     "that use ext-session-lock only (Noctalia, swaylock) should call "
                     "edgeware pause/resume from a lock hook instead."))
        general.add(AdwSwitchRow(
            "Pause During Screen Share", vars.pause_on_screenshare,
            subtitle="Stop spawning popups while a screencast is active (niri only)."))
        general.add(AdwSwitchRow(
            "Pause On Battery", vars.pause_on_battery,
            subtitle="Stop spawning popups while running on battery; resume on AC."))
        general.add(AdwSwitchRow(
            "Warn if \"Dangerous\" Settings Active", vars.safe_mode,
            subtitle="Asks you to confirm before saving if certain settings are enabled."))
        general.add(AdwSwitchRow(
            "Disable Config Help Messages", vars.message_off,
            subtitle="Hide the descriptive help text shown under settings and groups."))

        pause_apps_row = Adw.EntryRow(title="Pause for Focused Apps")
        pause_apps_row.set_text(str(vars.pause_apps.get()))
        pause_apps_row.set_tooltip_text(
            "Comma-separated app IDs (e.g. zoom, obs). Popups pause while one of "
            "these is focused. niri only. Tip: niri msg focused-window shows the app ID.")
        pause_apps_row.connect("changed", lambda r: vars.pause_apps.set(r.get_text()))
        general.add(pause_apps_row)

        # ---- Config presets ----------------------------------------------
        preset_group = Adw.PreferencesGroup(title="Config Presets", description=PRESET_TEXT)
        self.add(preset_group)

        preset_list = list_presets()
        self._presets_found = bool(preset_list)
        self._preset_list = preset_list

        self._preset_row = Adw.ComboRow(title="Preset")
        self._preset_row.set_model(Gtk.StringList.new(
            preset_list if preset_list else ["No presets found"]))
        self._preset_row.set_sensitive(self._presets_found)
        self._preset_row.connect("notify::selected", self._on_preset_selected)
        preset_group.add(self._preset_row)

        # Description
        self._preset_desc_row = Adw.ActionRow(title="Description")
        self._preset_desc_row.set_subtitle(
            load_preset_description(preset_list[0]) if self._presets_found else "")
        preset_group.add(self._preset_desc_row)

        # Actions row: Load (opens diff modal), Save, Delete
        actions_row = Adw.ActionRow(title="Actions")
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        self.load_preset_btn = Gtk.Button(label="Preview & Load…")
        self.load_preset_btn.add_css_class("suggested-action")
        self.load_preset_btn.set_sensitive(self._presets_found)
        self.load_preset_btn.connect("clicked", self._on_load_preset)
        btn_box.append(self.load_preset_btn)

        save_preset_btn = Gtk.Button(icon_name="document-save-as-symbolic")
        save_preset_btn.set_tooltip_text("Save current settings as a new preset")
        save_preset_btn.connect("clicked", lambda btn: save_preset(btn))
        btn_box.append(save_preset_btn)

        self._delete_preset_btn = Gtk.Button(icon_name="user-trash-symbolic")
        self._delete_preset_btn.add_css_class("destructive-action")
        self._delete_preset_btn.set_tooltip_text("Delete this preset")
        self._delete_preset_btn.set_sensitive(self._presets_found)
        self._delete_preset_btn.connect("clicked", self._on_delete_preset)
        btn_box.append(self._delete_preset_btn)

        actions_row.add_suffix(btn_box)
        preset_group.add(actions_row)

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

    def _current_preset_name(self) -> str | None:
        if not self._presets_found:
            return None
        model = self._preset_row.get_model()
        return model.get_string(self._preset_row.get_selected())

    def _on_preset_selected(self, row: Adw.ComboRow, _param) -> None:
        if not self._presets_found:
            return
        name = self._current_preset_name()
        self._preset_desc_row.set_subtitle(load_preset_description(name))

    def _on_load_preset(self, _btn: Gtk.Button) -> None:
        name = self._current_preset_name()
        if not name:
            return
        self._show_preset_diff_modal(name)

    def _show_preset_diff_modal(self, name: str) -> None:
        from config.gtk_window.preset import show_config_diff
        show_config_diff(
            self.get_root(),
            f"Load Preset: {name}",
            load_preset_description(name),
            compute_preset_diff(name, self._vars),
            "Apply Preset",
            lambda: apply_preset(load_preset(name), self._vars),
        )

    def _on_delete_preset(self, _btn: Gtk.Button) -> None:
        name = self._current_preset_name()
        if not name:
            return
        from gtk_dialog import ask_yes_no
        if not ask_yes_no(
            "Delete Preset",
            f'Delete preset "{name}"? This cannot be undone.',
            heading="Confirm deletion",
        ):
            return
        delete_preset(name)
        # Rebuild preset list
        new_list = list_presets()
        self._preset_list = new_list
        self._presets_found = bool(new_list)
        self._preset_row.set_model(Gtk.StringList.new(
            new_list if new_list else ["No presets found"]))
        self._preset_row.set_sensitive(self._presets_found)
        self.load_preset_btn.set_sensitive(self._presets_found)
        self._delete_preset_btn.set_sensitive(self._presets_found)
        self._diff_expander.set_sensitive(self._presets_found)
        if new_list:
            self._preset_desc_row.set_subtitle(load_preset_description(new_list[0]))
            self._refresh_diff(new_list[0])
        else:
            self._preset_desc_row.set_subtitle("")
            self._diff_expander.set_title("Preview Changes")
