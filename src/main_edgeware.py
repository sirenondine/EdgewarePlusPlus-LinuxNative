# Copyright (C) 2024 Araten & Marigold
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
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

if __name__ == "__main__":
    import os
    import sys

    # gtk4-layer-shell must be loaded before libwayland-client, which PyGObject
    # would otherwise pull in first. Re-exec ourselves with it LD_PRELOAD-ed.
    if "gtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
        import ctypes.util
        import glob

        lib = ctypes.util.find_library("gtk4-layer-shell")
        if not lib:
            appdir = os.environ.get("APPDIR", "")
            candidates = (glob.glob(f"{appdir}/usr/lib*/libgtk4-layer-shell.so*") if appdir else []) \
                + glob.glob("/usr/lib*/libgtk4-layer-shell.so*") \
                + glob.glob("/usr/lib/*/libgtk4-layer-shell.so*")
            lib = candidates[0] if candidates else None
        if lib:
            os.environ["LD_PRELOAD"] = (os.environ.get("LD_PRELOAD", "") + " " + lib).strip()
            os.execv(sys.executable, [sys.executable, *sys.argv])

    # Wayland-only (layer-shell popups require it). Must precede GTK import.
    if "GDK_BACKEND" not in os.environ:
        os.environ["GDK_BACKEND"] = "wayland"

    # Use the GL renderer — the Vulkan renderer spams VK_SUBOPTIMAL_KHR warnings
    # as popups spawn/resize. Must precede GTK import.
    if "GSK_RENDERER" not in os.environ:
        os.environ["GSK_RENDERER"] = "gl"

from threading import Thread

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gio, GLib, Gtk

# Give standalone runtime windows (the warning/safeword dialogs) a stable Wayland
# app-id instead of the bare "python3", so compositors can target them (e.g. a
# niri float rule). Must be set before any window is created.
GLib.set_prgname("io.github.sirenondine.EdgewarePlusPlusRuntime")

import utils
from config import first_launch_configure
from config.settings import Settings
from features.audio import play_audio
from features.corruption import corruption_danger_check, handle_corruption
from features.drive import fill_drive, replace_images
from features.hibernate import main_hibernate, start_main_hibernate
from features.image_popup import ImagePopup
from features.lockscreen import handle_lock_screen
from features.niri_watch import handle_niri_watch
from features.power import handle_power
from features.misc import (
    handle_discord,
    handle_keyboard,
    handle_mitosis_mode,
    handle_panic_lockout,
    handle_sextoy,
    handle_wallpaper,
    make_desktop_icons,
    make_tray_icon,
    open_web,
    send_notification,
)
from features.prompt import Prompt
from features.startup_splash import StartupSplash
from features.subliminal_popup import SubliminalPopup
from features.video_popup import VideoPopup
from pack import Pack
from panic import start_panic_listener
from roll import RollTarget, is_paused, roll_targets
from scripting import run_script
from state import State


def main(settings: Settings, pack: Pack, state: State, targets: list[RollTarget]) -> None:
    roll_targets(settings, targets)  # self-gates on pause
    if not is_paused():
        Thread(target=lambda: fill_drive(settings, pack, state), daemon=True).start()  # Thread for performance reasons
    if settings.escalation:
        from features import escalation
        delay = escalation.effective_delay(settings.delay)
    else:
        delay = settings.delay
    utils.after(delay, lambda: main(settings, pack, state, targets))


if __name__ == "__main__":
    utils.init_logging("main")

    first_launch_configure()

    settings = Settings()
    pack = Pack(settings.pack_path)
    state = State()

    settings.corruption_mode = settings.corruption_mode and pack.corruption_levels

    app = Gtk.Application(
        application_id="io.github.sirenondine.EdgewarePlusPlusRuntime",
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    def on_activate(app: Gtk.Application) -> None:
        app.hold()  # Keep the main loop alive — popups are standalone layer-shell windows

        corruption_danger_check(settings, pack)

        # TODO: Use a dict?
        targets = [
            RollTarget(lambda: ImagePopup(settings, pack, state), lambda: settings.image_chance if not settings.mitosis_mode else 0),
            RollTarget(lambda: VideoPopup(settings, pack, state), lambda: settings.video_chance if not settings.mitosis_mode else 0),
            RollTarget(lambda: SubliminalPopup(settings, pack), lambda: settings.subliminal_chance),
            RollTarget(lambda: Prompt(settings, pack, state), lambda: settings.prompt_chance),
            RollTarget(lambda: play_audio(settings, pack, state), lambda: settings.audio_chance),
            RollTarget(lambda: open_web(pack), lambda: settings.web_chance),
            RollTarget(lambda: send_notification(settings, pack, sextoy=state.sextoy), lambda: settings.notification_chance),
        ]

        def start_main() -> None:
            import perf
            perf.watchdog()
            make_tray_icon(settings, pack, state, lambda: main_hibernate(settings, pack, state, targets))
            make_desktop_icons(settings)
            handle_keyboard(settings, state)
            start_panic_listener(settings, state)
            Thread(target=lambda: replace_images(settings, pack), daemon=True).start()  # Thread for performance reasons
            handle_corruption(settings, pack, state)
            handle_discord(settings, pack)
            handle_sextoy(settings, state)
            handle_lock_screen(settings, state)
            handle_niri_watch(settings, state)
            handle_power(settings, state)
            handle_panic_lockout(settings, state)
            handle_mitosis_mode(settings, pack, state)
            run_script(settings, pack, state)

            if settings.hibernate_mode:
                start_main_hibernate(settings, pack, state, targets)
            else:
                handle_wallpaper(settings, pack, state)
                main(settings, pack, state, targets)

        if settings.startup_splash:
            StartupSplash(settings, pack, start_main)
        else:
            start_main()

    app.connect("activate", on_activate)
    app.run(None)
