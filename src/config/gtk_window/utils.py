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
import multiprocessing
import os
import shutil
import subprocess
import sys
import urllib.request
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Thread

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

import os_utils
import utils
from config import load_config
from config.items import CONFIG_DANGER, DangerLevel
from config.vars import ConfigVar, Vars
from paths import Data, Process
from pynput import keyboard

config = load_config()
log_file = utils.init_logging("config")


def keyboard_listener(connection: Connection) -> None:
    with keyboard.Listener(on_release=lambda key: connection.send(str(key))) as listener:
        connection.send("focus")
        listener.join()


def request_global_panic_key(button: Gtk.Button, var: ConfigVar) -> None:
    window = Gtk.Window(title="Key Listener")
    window.set_default_size(250, 250)
    window.set_resizable(False)
    window.set_modal(True)
    label = Gtk.Label(label="Press any key or close")
    label.set_vexpand(True)
    label.set_hexpand(True)
    window.set_child(label)

    parent_connection, child_connection = multiprocessing.Pipe()
    process = multiprocessing.Process(target=keyboard_listener, args=(child_connection,))
    process.start()

    def assign_panic_key(key: str) -> None:
        button.set_label(f"Set Global\nPanic Key\n<{key}>")
        var.set(key)
        window.close()

    def receive_panic_key() -> None:
        try:
            assert parent_connection.recv() == "focus"
            key = parent_connection.recv()
            window.connect("map", lambda _: assign_panic_key(key))
        except (EOFError, AssertionError):
            pass

    Thread(target=receive_panic_key).start()
    window.connect("close-request", lambda _: process.terminate())
    window.present()


def request_legacy_panic_key(button: Gtk.Button, var: ConfigVar) -> None:
    window = Gtk.Window(title="Key Listener")
    window.set_default_size(250, 250)
    window.set_resizable(False)
    window.set_modal(True)
    label = Gtk.Label(label="Press any key or close")
    label.set_vexpand(True)
    label.set_hexpand(True)
    window.set_child(label)

    key_controller = Gtk.EventControllerKey.new()
    key_controller.connect("key-pressed", lambda c, k, _, __: assign_panic_key(k))
    window.add_controller(key_controller)

    def assign_panic_key(keyval: int) -> bool:
        key_name = Gtk.accelerator_name(keyval, 0)
        button.set_label(f"Set Legacy\nPanic Key\n<{key_name}>")
        var.set(key_name)
        window.close()
        return True

    window.present()


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True

    path_type = "directory" if path.is_dir() else "file"
    dialog = Gtk.MessageDialog(
        text=f'Path "{path}" already exists.',
        secondary_text=f"This {path_type} will be deleted and overwritten. Is this okay?",
        buttons=Gtk.ButtonsType.YES_NO,
        message_type=Gtk.MessageType.WARNING,
    )

    delete = shutil.rmtree if path.is_dir() else os.remove
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.YES:
        delete(path)
        return True
    return False


def get_live_version() -> str:
    url = "https://raw.githubusercontent.com/sirenondine/EdgewarePlusPlus-LinuxNative/main/assets/default_config.json"
    test = config.get("toggleInternet", 0)
    if test != 0:
        logging.info("GitHub connection is disabled, version will not be checked.")
        return ""

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read())["versionplusplus"]
    except Exception as e:
        logging.warning(f"Failed to fetch version on GitHub.\n\tReason: {e}")
        return ""


def write_save(vars: Vars, exit_at_end: bool = False) -> None:
    if vars.safe_mode.get() and exit_at_end and not safe_check(vars):
        return

    logging.info("starting config save write...")
    temp = config.copy()
    temp["wallpaperDat"] = str(config["wallpaperDat"])

    os_utils.toggle_run_at_startup(vars.run_at_startup.get())

    for key, var in vars.entries.items():
        value = var.get()
        if key == "packPath":
            value = value if value != "default" else None
        temp[key] = (1 if value else 0) if type(value) is bool else value

    with open(Data.CONFIG, "w") as file:
        file.write(json.dumps(temp))
        logging.info(f"wrote config file: {json.dumps(temp)}")

    if not (len(sys.argv) > 1 and sys.argv[1] == "--first-launch-configure") and vars.run_on_save_quit.get() and exit_at_end:
        subprocess.Popen([sys.executable, Process.MAIN])

    if exit_at_end:
        logging.info("exiting config")
        sys.exit()
    else:
        dialog = Gtk.MessageDialog(text="Success!", secondary_text="Settings saved successfully!", buttons=Gtk.ButtonsType.OK)
        dialog.run()
        dialog.destroy()


def safe_check(vars: Vars) -> bool:
    danger_levels = {
        DangerLevel.EXTREME: [],
        DangerLevel.MAJOR: [],
        DangerLevel.MEDIUM: [],
        DangerLevel.MINOR: [],
    }

    for key, var in vars.entries.items():
        danger = CONFIG_DANGER.get(key)
        if danger and danger.check(var.get()):
            danger_levels[danger.level].append(f"\n\u2022{danger.warning or key}")

    danger_num = 0
    warnings = ""
    for level, dangers in danger_levels.items():
        danger_num += len(dangers)
        if dangers:
            warnings += f"\n\n{level.value.capitalize()}{''.join(dangers)}"

    if not danger_num:
        return True

    dialog = Gtk.MessageDialog(
        text=f"{danger_num} potentially dangerous setting(s) detected! Do you want to save anyway?",
        secondary_text=warnings,
        buttons=Gtk.ButtonsType.YES_NO,
        message_type=Gtk.MessageType.WARNING,
    )
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


def clear_launches(confirmation: bool) -> None:
    try:
        if os.path.exists(Data.CORRUPTION_LAUNCHES):
            os.remove(Data.CORRUPTION_LAUNCHES)
            if confirmation:
                dialog = Gtk.MessageDialog(
                    text="Cleaning Completed",
                    secondary_text="The file that manages corruption launches has been deleted, and will be remade next time you start Edgeware with corruption on!",
                    buttons=Gtk.ButtonsType.OK,
                )
                dialog.run()
                dialog.destroy()
        else:
            if confirmation:
                dialog = Gtk.MessageDialog(
                    text="No launches file!",
                    secondary_text="There is no launches file to delete!\n\nThe launches file is used for the launch transition mode, and is automatically deleted when you load a new pack.",
                    buttons=Gtk.ButtonsType.OK,
                )
                dialog.run()
                dialog.destroy()
    except Exception as e:
        print(f"failed to clear launches. {e}")
        logging.warning(f"could not delete the corruption launches file. {e}")


def refresh() -> None:
    subprocess.Popen([sys.executable, Process.CONFIG])
    sys.exit()
