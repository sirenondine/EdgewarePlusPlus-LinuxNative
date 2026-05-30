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
import os
import tempfile
from multiprocessing.connection import Client, Listener
from threading import Thread

from config.settings import Settings
from os_utils import set_wallpaper
from paths import CustomAssets
from state import State

AUTHKEY = b"Edgeware++"
PANIC_MESSAGE = "panic"
PAUSE_MESSAGE = "pause"
RESUME_MESSAGE = "resume"
TOGGLE_MESSAGE = "toggle"
STATUS_MESSAGE = "status"


def _socket_path() -> str:
    # XDG_RUNTIME_DIR is per-user, mode 0700, and cleared on logout — ideal for
    # an IPC socket. Falls back to a temp dir if it isn't set.
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime, "edgeware-panic.sock")


def panic(settings: Settings, state: State, condition: bool = True, disable: bool = True) -> None:
    def do_panic() -> None:
        if (disable and settings.panic_disabled) or not condition:
            return

        if settings.panic_lockout and state.panic_lockout_active:
            from gtk_dialog import ask_password
            password = ask_password("Panic — Safeword Required", "Enter safeword to unlock panic:")
            if password != settings.panic_lockout_password:
                return

        # Each cleanup step is isolated so a failure (e.g. wallpaper revert
        # erroring on some compositors) can never stop the app from quitting.
        try:
            set_wallpaper(CustomAssets.panic_wallpaper())
        except Exception as e:
            logging.warning(f"panic: failed to revert wallpaper: {e}")

        try:
            if state.keyboard_process:
                state.keyboard_process.terminate()
        except Exception:
            pass

        if getattr(state, "sextoy", None):
            try:
                state.sextoy.disconnect()
            except Exception:
                pass

        try:
            if state.tray and hasattr(state.tray, "stop"):
                state.tray.stop()
        except Exception:
            pass

        for player in state.audio_players.copy():
            try:
                player.stop()
            except Exception:
                pass

        from gi.repository import Gio
        app = Gio.Application.get_default()
        if app:
            app.quit()
        else:
            import os
            os._exit(0)

    from gi.repository import GLib
    GLib.idle_add(do_panic)


def emergency_stop(settings: Settings) -> None:
    """Hard panic: revert the wallpaper and exit the process immediately.

    Unlike panic(), this does not touch GTK or wait for the GLib main loop, so
    it works even when the loop is saturated (e.g. a popup flood). set_wallpaper
    only spawns subprocesses, so it is safe to call from any thread."""
    import os
    try:
        set_wallpaper(CustomAssets.panic_wallpaper())
    except Exception as e:
        logging.warning(f"emergency_stop: wallpaper revert failed: {e}")
    os._exit(0)


def request_panic(settings: Settings, state: State) -> None:
    """Panic entry point for the tray and socket. Honours panic lockout (which
    needs a GTK safeword prompt, so it goes through the graceful path), but
    otherwise hard-stops immediately and reliably."""
    if getattr(settings, "panic_lockout", False) and getattr(state, "panic_lockout_active", False):
        panic(settings, state, disable=False)
    else:
        emergency_stop(settings)


def _sync_tray_pause(state: State) -> None:
    """Update the tray's pause label to match the current state (on the main loop)."""
    from gi.repository import GLib

    def update() -> bool:
        import roll
        if getattr(state, "tray", None) and hasattr(state.tray, "set_pause_label"):
            state.tray.set_pause_label(roll.is_paused())
        return False

    GLib.idle_add(update)


def start_panic_listener(settings: Settings, state: State) -> None:
    path = _socket_path()

    def listen() -> None:
        # Remove a stale socket left behind by a previous crash.
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass

        try:
            import roll
            with Listener(address=path, family="AF_UNIX", authkey=AUTHKEY) as listener:
                while True:
                    with listener.accept() as connection:
                        message = connection.recv()
                        if message == PANIC_MESSAGE:
                            request_panic(settings, state)
                        elif message in (PAUSE_MESSAGE, RESUME_MESSAGE, TOGGLE_MESSAGE):
                            if message == PAUSE_MESSAGE:
                                roll.set_paused(True)
                            elif message == RESUME_MESSAGE:
                                roll.set_paused(False)
                            else:
                                roll.toggle_paused()
                            _sync_tray_pause(state)
                        elif message == STATUS_MESSAGE:
                            connection.send({
                                "running": True,
                                "paused": roll.is_paused(),
                                "popups": getattr(state, "popup_number", 0),
                                "hibernating": getattr(state, "hibernate_active", False),
                            })
        except OSError as e:
            logging.warning(f"Failed to start panic listener: {e}")

    Thread(target=listen, daemon=True).start()


def _send(message: str) -> bool:
    """Send a control message to a running runtime. Returns False if none."""
    path = _socket_path()
    try:
        with Client(address=path, family="AF_UNIX", authkey=AUTHKEY) as connection:
            connection.send(message)
        return True
    except (FileNotFoundError, ConnectionRefusedError):
        logging.info(f"No running Edgeware++ instance for '{message}' (socket absent).")
        return False


def send_panic() -> None:
    _send(PANIC_MESSAGE)


def send_pause() -> bool:
    return _send(PAUSE_MESSAGE)


def send_resume() -> bool:
    return _send(RESUME_MESSAGE)


def send_toggle_pause() -> bool:
    return _send(TOGGLE_MESSAGE)


def query_status() -> dict | None:
    """Ask a running runtime for its status. Returns None if not running."""
    path = _socket_path()
    try:
        with Client(address=path, family="AF_UNIX", authkey=AUTHKEY) as connection:
            connection.send(STATUS_MESSAGE)
            if connection.poll(2.0):
                return connection.recv()
    except (FileNotFoundError, ConnectionRefusedError, EOFError):
        pass
    return None


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "panic"
    if cmd == "status":
        status = query_status()
        if status is None:
            print("Edgeware is not running.")
        else:
            print(
                f"running   : yes\n"
                f"paused    : {'yes' if status.get('paused') else 'no'}\n"
                f"popups    : {status.get('popups', 0)}\n"
                f"hibernating: {'yes' if status.get('hibernating') else 'no'}"
            )
    else:
        _send({
            "pause": PAUSE_MESSAGE,
            "resume": RESUME_MESSAGE,
            "toggle": TOGGLE_MESSAGE,
        }.get(cmd, PANIC_MESSAGE))
