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
import subprocess
import sys
import urllib.request
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

import os_utils
import utils
from config import load_config
from config.items import CONFIG_DANGER, DangerLevel
from config.vars import ConfigVar, Vars
from paths import Data, Process

config = load_config()
log_file = utils.init_logging("config")


def _ensure_config_css() -> None:
    """Load all static config-window CSS once. Safe to call multiple times."""
    if getattr(_ensure_config_css, "_done", False):
        return
    _ensure_config_css._done = True  # type: ignore[attr-defined]
    from gi.repository import Gdk
    provider = Gtk.CssProvider()
    provider.load_from_string("""
        /* SettingsWindow */
        .version-mismatch { color: @warning_color; font-weight: bold; }
        .loading-overlay   { background: alpha(@window_bg_color, 0.85); }
        .danger-confirm    { background-color: alpha(@warning_color, 0.16); padding: 8px 12px; }
        /* HomeTab */
        .home-pill {
            background-color: alpha(@accent_bg_color, 0.18);
            color: @accent_fg_color;
            border-radius: 999px;
            padding: 4px 12px;
            margin: 2px;
        }
        .home-pill.dim { background-color: alpha(@window_fg_color, 0.10); color: @window_fg_color; }
        .home-hero     { padding: 16px; }
        .home-hero-art { border-radius: 12px; }
    """)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def _get_parent_window():
    from gi.repository import Gio
    app = Gio.Application.get_default()
    if app:
        return app.get_active_window()
    return None


def dialog_run(dialog: Gtk.Dialog) -> Gtk.ResponseType:
    """GTK4-compatible blocking dialog using a nested GLib main loop."""
    loop = GLib.MainLoop()
    result = [Gtk.ResponseType.DELETE_EVENT]

    def on_response(_d, r):
        result[0] = r
        if loop.is_running():
            loop.quit()

    def on_close(_d):
        if loop.is_running():
            loop.quit()
        return False

    dialog.connect("response", on_response)
    dialog.connect("close-request", on_close)
    loop.run()
    return result[0]


# Stored panic keys use pynput's str(key) form ("'a'", "Key.f9") so they match
# what the runtime panic listeners compare against: the GlobalShortcuts portal
# hint (_to_trigger) and the evdev fallback (key == settings.global_panic_key).
_GDK_NAME_TO_PYNPUT = {
    "space": "Key.space",
    "Return": "Key.enter",
    "KP_Enter": "Key.enter",
    "Escape": "Key.esc",
    "Tab": "Key.tab",
    "BackSpace": "Key.backspace",
    "Delete": "Key.delete",
    "Insert": "Key.insert",
    "Home": "Key.home",
    "End": "Key.end",
    "Page_Up": "Key.page_up",
    "Page_Down": "Key.page_down",
    "Up": "Key.up",
    "Down": "Key.down",
    "Left": "Key.left",
    "Right": "Key.right",
    "Caps_Lock": "Key.caps_lock",
    "Menu": "Key.menu",
    "Shift_L": "Key.shift_l",
    "Shift_R": "Key.shift_r",
    "Control_L": "Key.ctrl_l",
    "Control_R": "Key.ctrl_r",
    "Alt_L": "Key.alt_l",
    "Alt_R": "Key.alt_r",
    "ISO_Level3_Shift": "Key.alt_gr",
    "Super_L": "Key.cmd",
    "Super_R": "Key.cmd_r",
}


def _keyval_to_pynput(keyval: int) -> str:
    """Convert a GTK keyval to pynput's str(key) form (e.g. "'a'", "Key.f9")."""
    from gi.repository import Gdk

    unicode_point = Gdk.keyval_to_unicode(keyval)
    if unicode_point:
        char = chr(unicode_point)
        if char.isprintable() and not char.isspace():
            return f"'{char.lower()}'"

    name = Gdk.keyval_name(keyval) or ""
    if len(name) >= 2 and name[0] in "Ff" and name[1:].isdigit():
        return f"Key.{name.lower()}"  # function keys F1..F35
    return _GDK_NAME_TO_PYNPUT.get(name, f"Key.{name.lower()}")


def pretty_panic_key(stored: str) -> str:
    """Human-friendly label for a stored panic key (e.g. "'a'" -> "A")."""
    if not stored:
        return "None"
    if len(stored) >= 2 and stored[0] == "'" and stored[-1] == "'":
        return stored[1:-1].upper()
    if stored.startswith("Key."):
        return stored[4:].upper()
    return stored


def request_global_panic_key(button: Gtk.Button, var: ConfigVar) -> None:
    # Capture the key with GTK's own key controller. This works without any
    # privileges; the old pynput/uinput capture silently failed for users not in
    # the 'input' group, so the dialog never read a keypress. The captured value
    # is stored in pynput's str() format so the runtime portal/evdev panic
    # listeners recognise it.
    dialog = Adw.Dialog()
    dialog.set_title("Set Panic Key")
    dialog.set_content_width(340)
    dialog.set_content_height(200)

    status = Adw.StatusPage(
        icon_name="input-keyboard-symbolic",
        title="Press any key",
        description="That key will become the panic hotkey.\nClose to cancel.",
    )
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(status)
    dialog.set_child(tv)

    def on_key_pressed(_controller, keyval: int, _keycode: int, _state) -> bool:
        stored = _keyval_to_pynput(keyval)
        var.set(stored)
        button.set_label(f"<{pretty_panic_key(stored)}>")
        dialog.close()
        return True

    controller = Gtk.EventControllerKey.new()
    controller.connect("key-pressed", on_key_pressed)
    dialog.add_controller(controller)
    dialog.present(button.get_root())


def request_legacy_panic_key(button: Gtk.Button, var: ConfigVar) -> None:
    dialog = Adw.Dialog()
    dialog.set_title("Key Listener")
    dialog.set_content_width(300)
    dialog.set_content_height(160)

    status = Adw.StatusPage(
        icon_name="input-keyboard-symbolic",
        title="Press any key",
        description="Close to cancel.",
    )
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(status)
    dialog.set_child(tv)

    def assign_panic_key(keyval: int) -> bool:
        key_name = Gtk.accelerator_name(keyval, 0)
        button.set_label(f"Set Legacy\nPanic Key\n<{key_name}>")
        var.set(key_name)
        dialog.close()
        return True

    key_controller = Gtk.EventControllerKey.new()
    key_controller.connect("key-pressed", lambda c, k, _, __: assign_panic_key(k))
    dialog.add_controller(key_controller)
    dialog.present(button.get_root())


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True

    path_type = "directory" if path.is_dir() else "file"
    delete = shutil.rmtree if path.is_dir() else os.remove

    from gtk_dialog import ask_yes_no
    if ask_yes_no(
        "Confirm Overwrite",
        f'"{path}" already exists.\n\nThis {path_type} will be permanently deleted. Proceed?',
        heading="Overwrite existing file?",
        confirm_label="Overwrite",
        cancel_label="Cancel",
        destructive=True,
    ):
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


def persist(vars: Vars) -> None:
    """Write current settings to disk with no prompts or exit. Used by live
    autosave; danger confirmation happens inline at edit time, not here."""
    temp = config.copy()
    temp["wallpaperDat"] = str(config["wallpaperDat"])
    os_utils.toggle_run_at_startup(vars.run_at_startup.get())
    for key, var in vars.entries.items():
        value = var.get()
        if key == "packPath":
            value = value if value != "default" else None
        temp[key] = (1 if value else 0) if type(value) is bool else value
    # Atomic write so a running instance watching the file never reads a torn
    # half-written config (see Settings hot-reload).
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(Data.CONFIG.parent), suffix=".tmp")
    with os.fdopen(fd, "w") as file:
        file.write(json.dumps(temp))
    os.replace(tmp, Data.CONFIG)


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

    window = _get_parent_window()
    if window and hasattr(window, "clear_dirty"):
        window.clear_dirty()

    if not (len(sys.argv) > 1 and sys.argv[1] == "--first-launch-configure") and vars.run_on_save_quit.get() and exit_at_end:
        subprocess.Popen([sys.executable, Process.MAIN])

    if exit_at_end:
        logging.info("exiting config")
        from gi.repository import Gio
        app = Gio.Application.get_default()
        if app:
            app.quit()
        else:
            sys.exit()
    else:
        from config.gtk_window.toast import toast
        toast("Settings saved")


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
            danger_levels[danger.level].append(danger.warning or key)

    danger_num = 0
    warnings = ""
    for level, dangers in danger_levels.items():
        danger_num += len(dangers)
        if dangers:
            from gi.repository import GLib
            escaped = "".join(f"\n• {GLib.markup_escape_text(d)}" for d in dangers)
            warnings += f"\n\n<b>{GLib.markup_escape_text(level.value.capitalize())}</b>{escaped}"

    if not danger_num:
        return True

    from gtk_dialog import ask_yes_no
    return ask_yes_no(
        "Dangerous Settings",
        f"<b>{danger_num}</b> potentially dangerous setting(s) are active:{warnings}",
        heading="Save anyway?",
        markup=True,
        confirm_label="Save Anyway",
        cancel_label="Cancel",
    )


def clear_launches(confirmation: bool) -> None:
    from gtk_dialog import show_info
    try:
        if os.path.exists(Data.CORRUPTION_LAUNCHES):
            os.remove(Data.CORRUPTION_LAUNCHES)
            if confirmation:
                show_info(
                    "Launches Reset",
                    "The corruption launches file has been deleted. "
                    "It will be recreated the next time Edgeware runs with corruption enabled.",
                    heading="Done",
                )
        else:
            if confirmation:
                show_info(
                    "No Launches File",
                    "There is no launches file to delete.\n\n"
                    "The launches file tracks the Launch trigger mode and is "
                    "automatically removed when you load a new pack.",
                    heading="Nothing to reset",
                )
    except Exception as e:
        print(f"failed to clear launches. {e}")
        logging.warning(f"could not delete the corruption launches file. {e}")


def refresh() -> None:
    # os.execv atomically replaces the current process with a fresh config
    # instance — no spawn/exit gap, no brief window disappearance.
    import atexit
    args = [sys.executable, str(Process.CONFIG)]
    from gi.repository import Gio
    app = Gio.Application.get_default()
    if app:
        atexit.register(lambda: os.execv(sys.executable, args))
        app.quit()
    else:
        os.execv(sys.executable, args)
