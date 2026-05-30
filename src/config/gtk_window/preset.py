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


def compute_preset_diff(name: str, vars: Vars) -> list[tuple[str, str, str]]:
    """Return (friendly_name, current_value, new_value) for each setting the
    preset would change relative to the current live values."""
    preset = load_preset(name)
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
