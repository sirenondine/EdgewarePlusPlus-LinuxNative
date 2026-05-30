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

import logging
import multiprocessing
import os
import random
import time
import webbrowser
from collections.abc import Callable
from multiprocessing.connection import Connection
from threading import Thread

import utils

from config.settings import Settings
import os_utils
from os_utils import make_shortcut, set_wallpaper
from pack import Pack
from panic import panic, request_panic
from paths import CustomAssets, Process
from roll import roll
from state import State



_notifier = None  # lazily built DesktopNotifierSync (deferred import)


def notify(title: str, message: str, icon=None, attachment=None) -> None:
    """Send a desktop notification through a single shared notifier."""
    global _notifier
    from desktop_notifier.common import Attachment, Icon  # deferred (~40ms)
    from desktop_notifier.sync import DesktopNotifierSync
    if _notifier is None:
        _notifier = DesktopNotifierSync(app_name="Edgeware++")
    _notifier.send(
        title=title,
        message=message,
        icon=Icon(icon) if icon else None,
        attachment=Attachment(attachment) if attachment else None,
    )


def open_web(pack: Pack, web: str | None = None) -> None:
    web = web or pack.random_web()
    if web:
        # webbrowser.open can pause Edgeware if opening the browser takes a long time
        Thread(target=lambda: webbrowser.open(web), daemon=True).start()


def handle_sextoy(settings: Settings, state: State) -> None:
    """Connect to Intiface at startup if toy support is configured. The Sextoy
    lives on state so popups can drive it. No-op without buttplug-py or any
    configured devices."""
    from features.sextoy import BUTTPLUG_AVAILABLE, Sextoy

    if not BUTTPLUG_AVAILABLE or not getattr(settings, "sextoys", None):
        return
    state.sextoy = Sextoy(settings)

    def on_status(connected: bool) -> None:
        # Fired from the asyncio thread — marshal UI work to the main thread.
        from gi.repository import GLib

        def update() -> None:
            notify("Edgeware++", "Toy connected." if connected else "Toy disconnected. Reconnect from the tray menu.")
            if state.tray and hasattr(state.tray, "set_toy_status"):
                state.tray.set_toy_status(connected)
            return False

        GLib.idle_add(update)

    state.sextoy.on_status_change = on_status
    state.sextoy.connect()


def send_notification(
    settings: Settings, pack: Pack, notification: str | None = None, sextoy: object | None = None
) -> None:
    notification = notification or pack.random_notification()
    if not notification:
        return

    image = pack.random_image()
    notify(
        pack.info.name,
        notification,
        icon=pack.icon,
        attachment=image if roll(settings.notification_image_chance) and image else None,
    )

    from features.vibration_mixin import vibrate_event
    vibrate_event("display_notification", settings, sextoy)


def make_tray_icon(
    settings: Settings,
    pack: Pack,
    state: State,
    hibernate_activity: Callable[[], None],
) -> None:
    """Create a native StatusNotifierItem tray icon (Wayland + X11).

    Left click panics; middle click skips to hibernate (when enabled)."""
    from features.tray import StatusNotifierItem

    def skip_hibernate() -> None:
        if state.hibernate_active:
            return
        utils.after_cancel(state.hibernate_id)
        hibernate_activity()

    def open_config() -> None:
        import subprocess
        import sys
        subprocess.Popen([sys.executable, Process.CONFIG])

    def toggle_pause() -> None:
        import roll
        paused = roll.toggle_paused()
        if state.tray and hasattr(state.tray, "set_pause_label"):
            state.tray.set_pause_label(paused)

    # Offer a reconnect entry only when toy support is actually usable.
    from features.sextoy import BUTTPLUG_AVAILABLE
    toy_configured = BUTTPLUG_AVAILABLE and getattr(settings, "sextoys", None)
    on_reconnect_toy = (lambda: state.sextoy and state.sextoy.reconnect()) if toy_configured else None

    try:
        state.tray = StatusNotifierItem(
            icon_name=os_utils.APP_ID,
            tooltip="Edgeware++ — click to panic",
            on_panic=lambda: request_panic(settings, state),
            on_skip_hibernate=skip_hibernate if settings.hibernate_mode else None,
            on_open_config=open_config,
            on_toggle_pause=toggle_pause,
            on_reconnect_toy=on_reconnect_toy,
            on_quit=lambda: request_panic(settings, state),
        )
        logging.info("Created StatusNotifierItem tray icon (D-Bus, with menu)")
    except Exception as e:
        logging.warning(f"Failed to create tray icon: {e}")
        state.tray = None


def make_desktop_icons(settings: Settings) -> None:
    # Always register the app with the desktop (shows in launchers); idempotent.
    os_utils.install_app_entries()

    # Optional copies on the user's Desktop.
    if settings.desktop_icons:
        make_shortcut("Edgeware++", Process.MAIN, CustomAssets.icon())
        make_shortcut("Edgeware++ Config", Process.CONFIG, CustomAssets.config_icon())
        make_shortcut("Edgeware++ Panic", Process.PANIC, CustomAssets.panic_icon())


def handle_wallpaper(settings: Settings, pack: Pack, state: State) -> None:
    def rotate(previous: str = None) -> None:
        if (
            settings.hibernate_fix_wallpaper
            and not state.hibernate_active
            and state.popup_number == 0
        ):
            return

        wallpapers = settings.wallpapers.copy()
        if previous:
            wallpapers.remove(previous)

        wallpaper = random.choice(wallpapers)
        set_wallpaper(pack.paths.root / wallpaper)

        t = settings.wallpaper_timer
        v = settings.wallpaper_variance
        utils.after(t + random.randint(-v, v), lambda: rotate(wallpaper))

    if settings.corruption_mode and settings.corruption_wallpaper:
        return

    if settings.rotate_wallpaper and len(settings.wallpapers) > 1:
        rotate()
    elif pack.wallpaper:
        set_wallpaper(pack.wallpaper)


def handle_discord(settings: Settings, pack: Pack) -> None:
    if not settings.show_on_discord:
        return

    try:
        from pypresence import Presence  # deferred (~30ms); Discord is off by default
        presence = Presence("820204081410736148")
        presence.connect()
        presence.update(
            state=pack.discord.text,
            large_image=pack.discord.image,
            start=int(time.time()),
        )
    except Exception as e:
        logging.warning(f"Setting Discord presence failed. Reason: {e}")


def handle_panic_lockout(settings: Settings, state: State) -> None:
    def panic_lockout_over() -> None:
        state.panic_lockout_active = False

    if settings.panic_lockout:
        state.panic_lockout_active = True
        utils.after(settings.panic_lockout_time, panic_lockout_over)


def mitosis_popup(settings: Settings, pack: Pack, state: State) -> None:
    # Imports done here to avoid circular imports
    from features.image_popup import ImagePopup
    from features.video_popup import VideoPopup

    try:
        popup = random.choices(
            [ImagePopup, VideoPopup],
            [settings.image_chance, settings.video_chance],
            k=1,
        )[0]
    except ValueError:
        popup = ImagePopup  # Exception thrown when both chances are 0
    popup(settings, pack, state)


def handle_mitosis_mode(settings: Settings, pack: Pack, state: State) -> None:
    if settings.mitosis_mode:

        def observer() -> None:
            if state.popup_number == 0:
                mitosis_popup(settings, pack, state)

        state._popup_number.attach(observer)
        mitosis_popup(settings, pack, state)


def keyboard_listener(connection: Connection) -> None:
    # Use pynput's uinput backend (reads /dev/input via python-evdev) — the only
    # one that works on Wayland. It needs read access to the input devices and a
    # readable console keymap (dumpkeys), so it fails for unprivileged users;
    # the GlobalShortcuts portal is the primary hotkey path and panic is also
    # available from the tray, the panic command and the config window.
    os.environ.setdefault("PYNPUT_BACKEND", "uinput")
    try:
        from pynput import keyboard
    except Exception as e:
        logging.warning(f"Keyboard panic hotkey fallback unavailable: {e}")
        return

    def callback(type: str) -> None:
        return lambda key: connection.send((type, str(key)))

    with keyboard.Listener(
        on_press=callback("press"), on_release=callback("release")
    ) as listener:
        listener.join()


def handle_keyboard(settings: Settings, state: State) -> None:
    # Prefer the GlobalShortcuts portal (Wayland-native, no /dev/input access).
    # Alt+click blacklisting reads GTK modifiers directly, so the portal path
    # doesn't need a global keyboard grab at all. If the compositor declines the
    # binding, fall back to evdev so panic still works.
    from features import global_shortcuts

    if global_shortcuts.portal_available():
        try:
            state._panic_shortcut = global_shortcuts.PanicShortcut(
                settings.global_panic_key,
                lambda: panic(settings, state, disable=False),
                on_failed=lambda: _start_evdev_keyboard(settings, state),
            )
            logging.info("Global panic hotkey requested via GlobalShortcuts portal")
            return
        except Exception as e:
            logging.warning(f"GlobalShortcuts portal failed, falling back to evdev: {e}")

    _start_evdev_keyboard(settings, state)


def _start_evdev_keyboard(settings: Settings, state: State) -> None:
    if getattr(state, "keyboard_process", None):
        return  # already running
    # pynput (evdev on Wayland — needs the 'input' group). Imported lazily: it
    # opens an X connection on import, which fails on pure Wayland / in sandboxes.
    try:
        from pynput import keyboard
    except Exception as e:
        logging.warning(f"Keyboard fallback unavailable (no pynput backend): {e}")
        return
    alt = [
        str(keyboard.Key.alt),
        str(keyboard.Key.alt_gr),
        str(keyboard.Key.alt_l),
        str(keyboard.Key.alt_r),
    ]

    parent_connection, child_connection = multiprocessing.Pipe()

    def receive() -> None:
        while True:
            try:
                type, key = parent_connection.recv()
            except EOFError:
                break  # Panic

            if type == "press" and key in alt:
                state.alt_held = True
            if type == "release":
                if key in alt:
                    state.alt_held = False
                panic(
                    settings, state, condition=(key == settings.global_panic_key)
                )

    state.keyboard_process = multiprocessing.Process(
        target=keyboard_listener, args=(child_connection,)
    )
    state.keyboard_process.start()

    Thread(target=receive).start()
