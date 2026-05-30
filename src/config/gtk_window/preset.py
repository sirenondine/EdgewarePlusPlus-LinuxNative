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
import os
from json.decoder import JSONDecodeError
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.vars import Vars
from config.gtk_window.toast import toast, name_popover
from paths import Data


def list_presets() -> list[str]:
    Data.PRESETS.mkdir(parents=True, exist_ok=True)
    return [preset.split(".")[0] for preset in os.listdir(Data.PRESETS) if preset.endswith(".cfg")]


def load_preset(name: str) -> dict:
    preset = Data.PRESETS / f"{name}.cfg"
    try:
        with open(preset, "r") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        logging.info(f"{preset.name} not found.")
    except JSONDecodeError as e:
        logging.warning(f"{preset.name} is not valid JSON. Reason: {e}")
    return {}


def load_preset_description(name: str) -> str:
    description = Data.PRESETS / f"{name}.txt"
    if not description.is_file():
        return "No description provided."
    with open(description, "r") as f:
        return f.read()


def delete_preset(name: str) -> bool:
    """Delete a preset's .cfg and .txt files. Returns True on success."""
    deleted = False
    for ext in (".cfg", ".txt"):
        p = Data.PRESETS / f"{name}{ext}"
        try:
            if p.is_file():
                p.unlink()
                deleted = True
        except Exception as e:
            logging.warning(f"Failed to delete {p}: {e}")
    return deleted


def compute_diff(preset: dict, vars: Vars) -> list[tuple[str, str, str]]:
    """Return (friendly_name, current_value, new_value) for each setting in
    `preset` that differs from the current live value."""
    changes = []
    for key, new_val in preset.items():
        var = vars.entries.get(key)
        if var is None:
            continue
        current = var.get()
        # Normalise booleans stored as ints
        cur_str = str(bool(current) if isinstance(new_val, bool) else current)
        new_str = str(new_val)
        if cur_str != new_str:
            friendly = key.replace("_", " ").title()
            changes.append((friendly, cur_str, new_str))
    return changes


def compute_preset_diff(name: str, vars: Vars) -> list[tuple[str, str, str]]:
    """compute_diff for a named preset on disk."""
    return compute_diff(load_preset(name), vars)


def show_config_diff(parent, title: str, description: str,
                     changes: list[tuple[str, str, str]],
                     apply_label: str, on_apply) -> None:
    """Modal that previews the settings a config change would make, then
    applies it on confirmation. Shared by the preset and pack-config loaders."""
    require_version("Adw", "1")
    from gi.repository import Adw

    win = Adw.Window()
    win.set_title(title)
    win.set_default_size(480, 520)
    win.set_modal(True)
    if parent is not None:
        win.set_transient_for(parent)

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_show_end_title_buttons(False)
    header.set_title_widget(Adw.WindowTitle(
        title=title,
        subtitle=(f"{len(changes)} setting{'s' if len(changes) != 1 else ''} will change"
                  if changes else "No changes from current settings"),
    ))
    toolbar_view.add_top_bar(header)
    win.set_content(toolbar_view)

    page = Adw.PreferencesPage()
    toolbar_view.set_content(page)

    if description:
        desc_group = Adw.PreferencesGroup(title="Description")
        page.add(desc_group)
        desc_row = Adw.ActionRow()
        desc_row.set_activatable(False)
        lbl = Gtk.Label(label=description, wrap=True, xalign=0)
        lbl.set_margin_start(12)
        lbl.set_margin_end(12)
        lbl.set_margin_top(8)
        lbl.set_margin_bottom(8)
        desc_row.set_child(lbl)
        desc_group.add(desc_row)

    changes_group = Adw.PreferencesGroup(
        title="Changes",
        description=("Settings that differ from your current configuration." if changes
                     else "This matches your current settings — nothing will change."),
    )
    page.add(changes_group)
    for friendly, current, new in changes:
        changes_group.add(Adw.ActionRow(title=friendly, subtitle=f"{current}  →  {new}"))

    btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_bar.set_margin_start(16)
    btn_bar.set_margin_end(16)
    btn_bar.set_margin_top(8)
    btn_bar.set_margin_bottom(16)
    btn_bar.set_halign(Gtk.Align.END)

    cancel_btn = Gtk.Button(label="Cancel")
    cancel_btn.connect("clicked", lambda _: win.close())
    btn_bar.append(cancel_btn)

    apply_btn = Gtk.Button(label=apply_label)
    apply_btn.add_css_class("suggested-action")
    apply_btn.connect("clicked", lambda _: (on_apply(), win.close()))
    btn_bar.append(apply_btn)

    toolbar_view.add_bottom_bar(btn_bar)
    win.present()


def save_preset(anchor: Gtk.Widget) -> None:
    """Save the current config as a named preset.  Uses name_popover so no
    deprecated Gtk.Dialog is needed."""
    def _do_save(preset_name: str) -> None:
        import shutil
        path = Data.PRESETS / f"{preset_name}.cfg"
        if path.exists():
            from gtk_dialog import ask_yes_no
            if not ask_yes_no(
                "Overwrite Preset",
                f'A preset named "{preset_name}" already exists. Overwrite it?',
                heading="Confirm overwrite",
            ):
                return
        try:
            Data.PRESETS.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Data.CONFIG, path)
            toast(f'Preset "{preset_name}" saved.')
        except Exception as e:
            logging.warning(f"Failed to save preset: {e}")

    name_popover(anchor, "Preset name", _do_save)


def apply_preset(preset: dict, vars: Vars, select: list[str] | None = None) -> None:
    danger = vars.preset_danger.get()
    select = select or list(vars.entries.keys())

    for key, value in preset.items():
        if key not in select:
            continue
        var = vars.entries.get(key)
        if var:
            var.set(int(value) if isinstance(value, bool) else value)

    if danger:
        vars.safe_mode.set(True)

    toast("Config preset loaded. Review changes before saving.")
