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

import os
from dataclasses import dataclass
from pathlib import Path

PATH = Path(__file__).parent.parent
DEFAULT_PACK_PATH = PATH / "resource"


def _xdg(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or os.path.expanduser(default))


# Backward compat: existing installs keep everything under <repo>/data (portable).
# Fresh installs follow the XDG Base Directory spec.
_LEGACY_DATA = PATH / "data"
_PORTABLE = _LEGACY_DATA.exists()

if _PORTABLE:
    _DATA_ROOT = _LEGACY_DATA
    _CONFIG_ROOT = _LEGACY_DATA
    _STATE_ROOT = _LEGACY_DATA
else:
    _DATA_ROOT = _xdg("XDG_DATA_HOME", "~/.local/share") / "edgeware"
    _CONFIG_ROOT = _xdg("XDG_CONFIG_HOME", "~/.config") / "edgeware"
    _STATE_ROOT = _xdg("XDG_STATE_HOME", "~/.local/state") / "edgeware"


@dataclass
class Process:
    ROOT = PATH / "src"

    CONFIG = ROOT / "main_config.py"
    MAIN = ROOT / "main_edgeware.py"
    PANIC = ROOT / "panic.py"


@dataclass
class Assets:
    ROOT = PATH / "assets"

    CORRUPTION_ABRUPT = ROOT / "corruption_abruptfade.png"
    CORRUPTION_DEFAULT = ROOT / "corruption_defaultfade.png"

    # Unchangeable defaults
    DEFAULT_CONFIG = ROOT / "default_config.json"
    DEFAULT_IMAGE = ROOT / "default_image.png"
    CENSOR_FONT = ROOT / "censor_font.ttf"  # bold TTF for burned-in censor captions (DejaVu Bold)
    FONT_ANTON = ROOT / "font_anton.ttf"
    FONT_BEBAS = ROOT / "font_bebasneue.ttf"
    FONT_FREDOKA = ROOT / "font_fredoka.ttf"
    FONT_PACIFICO = ROOT / "font_pacifico.ttf"
    FACE_LANDMARKS = ROOT / "landmarks_68_pfld.onnx"  # PFLD 68-pt model for precise eye bars
    NUDENET_MODEL = ROOT / "nudenet_detect.onnx"  # bundled NudeNet YOLOv8-detect (320px, 18 classes)
    BREASTS_MODEL = ROOT / "breasts_seg.onnx"  # Anzhc full-breast YOLOv8-seg (bundled)
    FACE_SEG = ROOT / "face_seg.onnx"  # Anzhc full-face YOLOv8-seg (bundled)
    # Single-class YOLOv8-seg models (bundled) feeding the generic seg registry.
    ARMPIT_SEG = ROOT / "armpit_seg.onnx"
    BELLY_SEG = ROOT / "belly_seg.onnx"
    MOUTH_SEG = ROOT / "mouth_seg.onnx"
    UNDERWEAR_SEG = ROOT / "underwear_seg.onnx"
    SOCKS_SEG = ROOT / "socks_seg.onnx"
    SKIN_SEG = ROOT / "skin_seg.onnx"

    # Changeable defaults
    DEFAULT_CONFIG_ICON = ROOT / "default_config_icon.ico"
    DEFAULT_HYPNO = ROOT / "default_hypno.gif"
    DEFAULT_ICON = ROOT / "default_icon.ico"
    DEFAULT_PANIC_ICON = ROOT / "default_panic_icon.ico"
    DEFAULT_PANIC_WALLPAPER = ROOT / "default_panic_wallpaper.jpg"
    DEFAULT_STARTUP_SPLASH = ROOT / "default_loading_splash.png"
    DEFAULT_THEME_DEMO = ROOT / "default_theme_demo.png"


@dataclass
class Data:
    ROOT = _DATA_ROOT

    # Directories
    BACKUPS = _DATA_ROOT / "backups"
    LOGS = _STATE_ROOT / "logs"
    MOODS = _DATA_ROOT / "moods"
    PACKS = _DATA_ROOT / "packs"
    PRESETS = _DATA_ROOT / "presets"
    BLACKLIST = _DATA_ROOT / "blacklist"

    # Files
    CONFIG = _CONFIG_ROOT / "config.json"
    ANIME_MODEL = _DATA_ROOT / "nsfw-anime-medium.onnx"  # optional anime NSFW detector (downloaded on demand)
    BODY_MODEL = _DATA_ROOT / "body_seg.onnx"  # optional whole-body seg (~105 MB, not bundled)
    CORRUPTION_LAUNCHES = _DATA_ROOT / "corruption_launches.dat"
    PROGRESS = _STATE_ROOT / "progress.json"  # local gamification stats
    COMPANION_MEMORY = _STATE_ROOT / "companion_memory.json"  # companion auto-memory facts

    # Changed defaults
    CONFIG_ICON = ROOT / "config_icon.ico"
    HYPNO = ROOT / "hypno.png"
    ICON = ROOT / "icon.ico"
    PANIC_ICON = ROOT / "panic_icon.ico"
    PANIC_WALLPAPER = ROOT / "panic_wallpaper.png"
    STARTUP_SPLASH = ROOT / "loading_splash.png"
    THEME_DEMO = ROOT / "theme_demo.png"


class CustomAssets:
    @staticmethod
    def config_icon() -> Path:
        return Data.CONFIG_ICON if Data.CONFIG_ICON.is_file() else Assets.DEFAULT_CONFIG_ICON

    @staticmethod
    def hypno() -> Path:
        return Data.HYPNO if Data.HYPNO.is_file() else Assets.DEFAULT_HYPNO

    @staticmethod
    def icon() -> Path:
        return Data.ICON if Data.ICON.is_file() else Assets.DEFAULT_ICON

    @staticmethod
    def panic_icon() -> Path:
        return Data.PANIC_ICON if Data.PANIC_ICON.is_file() else Assets.DEFAULT_PANIC_ICON

    @staticmethod
    def panic_wallpaper() -> Path:
        return Data.PANIC_WALLPAPER if Data.PANIC_WALLPAPER.is_file() else Assets.DEFAULT_PANIC_WALLPAPER

    @staticmethod
    def startup_splash() -> Path:
        return Data.STARTUP_SPLASH if Data.STARTUP_SPLASH.is_file() else Assets.DEFAULT_STARTUP_SPLASH

    @staticmethod
    def theme_demo() -> Path:
        return Data.THEME_DEMO if Data.THEME_DEMO.is_file() else Assets.DEFAULT_THEME_DEMO


@dataclass
class PackPaths:
    def __init__(self, root: Path) -> None:
        self.root = root

        # Directories
        self.audio = self.root / "aud"
        self.hypno = self.root / "hypno"
        self.image = self.root / "img"
        self.video = self.root / "vid"

        # Files
        self.config = self.root / "config.json"
        self.corruption = self.root / "corruption.json"
        self.discord = self.root / "discord.dat"
        self.icon = self.root / "icon.ico"
        self.index = self.root / "index.json"
        self.info = self.root / "info.json"
        self.script = self.root / "script.lua"
        self.splash = [self.root / f"loading_splash.{extension}" for extension in ["png", "gif", "jpg", "jpeg", "bmp"]]
        self.wallpaper = self.root / "wallpaper.png"
        self.companion = self.root / "companion.json"

        # Legacy fallback options
        self.hypno_legacy = self.root / "subliminals"
        self.captions = self.root / "captions.json"
        self.media = self.root / "media.json"
        self.prompt = self.root / "prompt.json"
        self.web = self.root / "web.json"
