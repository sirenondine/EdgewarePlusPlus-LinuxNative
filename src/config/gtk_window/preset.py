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
import shutil
from json.decoder import JSONDecodeError

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.vars import Vars
from config.gtk_window.toast import toast
from config.gtk_window.utils import confirm_overwrite
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
        return "This preset has no description file."
    with open(description, "r") as f:
        return f.read()


def save_preset() -> str | None:
    dialog = Gtk.Dialog(title="Save Preset")
    dialog.set_default_size(300, 100)
    entry = Gtk.Entry()
    entry.set_placeholder_text("Preset name")
    content = dialog.get_content_area()
    content.append(entry)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", Gtk.ResponseType.OK)

    result = [None]

    def on_response(d, r):
        if r == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                path = Data.PRESETS / f"{name}.cfg"
                if not confirm_overwrite(path):
                    return
                shutil.copyfile(Data.CONFIG, path)
                result[0] = name
        d.destroy()

    dialog.connect("response", on_response)
    dialog.present()


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
