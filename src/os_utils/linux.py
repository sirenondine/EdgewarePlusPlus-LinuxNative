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
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from os_utils.linux_utils import (
    find_get_wallpaper_command,
    find_set_wallpaper_commands,
    find_set_wallpaper_function,
    get_desktop_environment,
)
from paths import PATH, CustomAssets, Process

APP_ID = "io.github.sirenondine.EdgewarePlusPlus"


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))


def _launcher(name: str) -> str:
    """Absolute path to a launcher script (edgeware.sh / config.sh / panic.sh)."""
    return str(PATH / f"{name}.sh")


def get_wallpaper() -> Path | None:
    # Confirmed to work on:
    # - GNOME
    desktop = get_desktop_environment()
    command = find_get_wallpaper_command(desktop)

    if command:
        try:
            s = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        except Exception as e:
            logging.warning(f"Failed to run {command}. Reason: {e}")
            return None

        if s.stdout:
            line = s.stdout.readline()
            string = line.decode("utf-8").strip()[1:-1]
            return Path(urlparse(string).path)
    else:
        logging.info(f"Can't get wallpaper for desktop environment {desktop}")

    return None


def set_wallpaper(wallpaper: Path) -> None:
    # Confirmed to work on:
    # - GNOME
    desktop = get_desktop_environment()
    commands = find_set_wallpaper_commands(wallpaper, desktop)
    function = find_set_wallpaper_function(wallpaper, desktop)

    if len(commands) > 0:
        for command in commands:
            try:
                subprocess.Popen(command, shell=True)
            except Exception as e:
                logging.warning(f"Failed to run {command}. Reason: {e}")
    elif function:
        try:
            function()
        except Exception as e:
            logging.warning(f"Failed to set wallpaper. Reason: {e}")
    else:
        logging.info(f"Can't set wallpaper for desktop environment {desktop}")


def open_directory(url: str) -> None:
    subprocess.Popen(["xdg-open", url])


def _desktop_entry(name: str, exec_cmd: str, icon: str, wm_class: str | None = None, no_display: bool = False, mime_type: str | None = None) -> str:
    lines = [
        "[Desktop Entry]",
        "Version=1.0",  # freedesktop Desktop Entry spec version, not the app version
        f"Name={name}",
        f"Exec={exec_cmd}",
        f"Icon={icon}",
        "Terminal=false",
        "Type=Application",
        "Categories=Utility;",
    ]
    if wm_class:
        lines.append(f"StartupWMClass={wm_class}")
    if no_display:
        lines.append("NoDisplay=true")
    if mime_type:
        lines.append(f"MimeType={mime_type}")
    return "\n".join(lines) + "\n"


def _install_themed_icon() -> str:
    """Render the .ico app icon to a themed PNG under hicolor. Returns icon name."""
    try:
        from PIL import Image

        icon_dir = _xdg_data_home() / "icons" / "hicolor" / "256x256" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        target = icon_dir / f"{APP_ID}.png"
        img = Image.open(CustomAssets.icon()).convert("RGBA")
        img.thumbnail((256, 256))
        img.save(target)
        return APP_ID
    except Exception as e:
        logging.warning(f"Failed to install themed icon, falling back to file path: {e}")
        return str(CustomAssets.icon())


def install_app_entries() -> None:
    """Install XDG desktop entries to the applications dir so Edgeware++ shows
    up in app launchers. Idempotent."""
    icon = _install_themed_icon()
    apps_dir = _xdg_data_home() / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)

    entries = {
        f"{APP_ID}.desktop": _desktop_entry(
            "Edgeware++", _launcher("edgeware"), icon, wm_class=f"{APP_ID}Runtime"
        ),
        f"{APP_ID}.Config.desktop": _desktop_entry(
            "Edgeware++ Config", _launcher("config"), icon, wm_class=APP_ID
        ),
        f"{APP_ID}.Panic.desktop": _desktop_entry(
            "Edgeware++ Panic", _launcher("panic"), icon
        ),
        # "Open With" handler for pack zips — advertises the zip MIME so file
        # managers offer it, but NoDisplay keeps it out of app launchers and it
        # is never set as the default zip handler.
        f"{APP_ID}.Import.desktop": _desktop_entry(
            "Import as Edgeware++ Pack", f"{_launcher('config')} --import %f", icon,
            no_display=True, mime_type="application/zip",
        ),
    }
    for filename, content in entries.items():
        (apps_dir / filename).write_text(content)

    # Refresh caches (best-effort; harmless if the tools are missing).
    for cmd in (["update-desktop-database", str(apps_dir)],
                ["gtk-update-icon-cache", "-q", "-t", str(_xdg_data_home() / "icons" / "hicolor")]):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass


def make_shortcut(
    title: str, process: Path, icon: Path, location: Path | None = None
) -> None:
    """Write a single .desktop launcher (used for ~/Desktop copies and autostart)."""
    name_map = {
        Process.MAIN: "edgeware",
        Process.CONFIG: "config",
        Process.PANIC: "panic",
    }
    launcher = name_map.get(process)
    exec_cmd = _launcher(launcher) if launcher else shlex.join([str(sys.executable), str(process)])
    icon_name = _install_themed_icon()

    file = (location if location else Path(os.path.expanduser("~/Desktop"))) / f"{title}.desktop"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(_desktop_entry(title, exec_cmd, icon_name, wm_class=APP_ID))
    file.chmod(0o755)
    if get_desktop_environment() == "gnome":
        subprocess.run(
            f"gio set {shlex.quote(str(file.absolute()))} metadata::trusted true",
            shell=True,
        )


def toggle_run_at_startup(state: bool) -> None:
    autostart_path = Path(os.path.expanduser("~/.config/autostart"))
    if state:
        make_shortcut("Edgeware++", Process.MAIN, CustomAssets.icon(), autostart_path)
    else:
        (autostart_path / "Edgeware++.desktop").unlink(missing_ok=True)


def install_systemd_unit() -> bool:
    """Install the bundled systemd *user* unit. Opt-in alternative to the XDG
    autostart .desktop — gives journald logging and graphical-session lifecycle.
    Returns True on success. Enable with:
        systemctl --user enable --now edgeware.service
    """
    src = PATH / "systemd" / "edgeware.service"
    if not src.is_file():
        logging.warning("systemd unit template missing")
        return False
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    units_dir = config_home / "systemd" / "user"
    units_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, units_dir / "edgeware.service")
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass
    return True
