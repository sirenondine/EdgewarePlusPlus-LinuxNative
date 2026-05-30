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

        set_wallpaper(CustomAssets.panic_wallpaper())

        if state.keyboard_process:
            state.keyboard_process.terminate()

        if state.tray and hasattr(state.tray, "stop"):
            state.tray.stop()

        for player in state.audio_players.copy():
            try:
                player.stop()
            except Exception:
                pass

        from gi.repository import Gio
        app = Gio.Application.get_default()
        if app:
            app.quit()

    from gi.repository import GLib
    GLib.idle_add(do_panic)


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
            with Listener(address=path, family="AF_UNIX", authkey=AUTHKEY) as listener:
                while True:
                    with listener.accept() as connection:
                        message = connection.recv()
                        if message == PANIC_MESSAGE:
                            panic(settings, state, disable=False)
        except OSError as e:
            logging.warning(f"Failed to start panic listener: {e}")

    Thread(target=listen, daemon=True).start()


def send_panic() -> None:
    path = _socket_path()
    try:
        with Client(address=path, family="AF_UNIX", authkey=AUTHKEY) as connection:
            connection.send(PANIC_MESSAGE)
    except (FileNotFoundError, ConnectionRefusedError):
        logging.info("No running Edgeware++ instance to panic (socket absent).")


if __name__ == "__main__":
    send_panic()
