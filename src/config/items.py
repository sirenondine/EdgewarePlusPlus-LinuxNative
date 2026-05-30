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
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

import ast
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from voluptuous import All, Range, Schema, Union
from voluptuous.error import Invalid

# Sentinel marking a config item as user-editable in the config window. Only its
# truthiness is checked (see Vars), so a single shared value suffices.
VAR = True

BROKEN = True  # For config items that can't be changed by corruption

NONNEGATIVE = Schema(All(int, Range(min=0)))
PERCENTAGE = Schema(All(int, Range(min=0, max=100)))
BOOLEAN = Schema(All(int, Range(min=0, max=1)))
STRING = Schema(str)
FLOAT = Schema(All(Union(int, float), Range(min=0)))


def s_to_ms(value: int) -> int:
    return value * 1000


def to_float(value: int) -> float:
    return value / 100


def negation(value: bool) -> bool:
    return not value


class DangerLevel(Enum):
    EXTREME = "extreme"
    MAJOR = "major"
    MEDIUM = "medium"
    MINOR = "minor"


@dataclass
class Danger:
    level: DangerLevel
    schema: Schema  # When validation passes, the value is dangerous
    warning: str | None = None

    def check(self, value: object) -> bool:
        try:
            self.schema(value)
            return True
        except Invalid:
            return False


@dataclass
class Item:
    key: str
    schema: Callable
    var: Callable | None
    setting: Callable | None
    danger: Danger | None = None

    # TODO: Find a better solution for this
    block: bool = False


REPLACE_IMAGES_DANGER = "Replace Images is enabled! THIS WILL DELETE FILES ON YOUR COMPUTER! Only enable this willingly and cautiously! Read the documentation in the Dangerous tab!"
RUN_AT_STARTUP_DANGER = "Launch on PC Startup is enabled! This will run Edgeware when you start your computer!"
FILL_DRIVE_DANGER = "Fill Drive is enabled! Edgeware will place images all over your computer! Even if you want this, make sure the protected directories are right!"
PANIC_LOCKOUT_DANGER = "Panic Lockout is enabled! Panic cannot be used until a specific time! Make sure you know your Safeword!"
MITOSIS_MODE_DANGER = "Mitosis Mode is enabled! With high popup rates, this could create a chain reaction, causing lag!"
HIBERNATE_DELAY_MIN_DANGER = "You are running Hibernate Mode with a short minimum cooldown! You might experience lag if a bunch of hibernate modes overlap!"
HIBERNATE_DELAY_MAX_DANGER = "You are running Hibernate Mode with a short maximum cooldown! You might experience lag if a bunch of hibernate modes overlap!"
SHOW_ON_DISCORD_DANGER = "Show on Discord is enabled! This could lead to potential embarassment if you're on your main account!"
PANIC_DISABLED_DANGER = "Panic Hotkey is disabled! Panic is still available from the tray icon and the panic command."
RUN_ON_SAVE_QUIT_DANGER = "Edgeware will run on Save & Exit (AKA: when you hit Yes!)"


# fmt: off
CONFIG_ITEMS = {
    # Start
    "pack_path": Item("packPath", Schema(Union(str, None)), VAR, lambda value: value),
    "theme": Item("themeType", STRING, VAR, str),  # vestigial: never read at runtime (popups use GTK CSS)
    "theme_ignore_config": Item("themeNoConfig", BOOLEAN, VAR, None, block=True),
    "startup_splash": Item("showLoadingFlair", BOOLEAN, VAR, bool, block=True),
    "run_on_save_quit": Item("runOnSaveQuit", BOOLEAN, VAR, None, danger=Danger(DangerLevel.MINOR, Schema(1), RUN_ON_SAVE_QUIT_DANGER), block=True),
    "desktop_icons": Item("desktopIcons", BOOLEAN, VAR, bool, block=True),
    "safe_mode": Item("safeMode", BOOLEAN, VAR, None, block=True),
    "message_off": Item("messageOff", BOOLEAN, VAR, None, block=True),
    "global_panic_key": Item("globalPanicButton", STRING, VAR, str, block=True),  # while disabling panic could be used for danger-chasing fetishists, changing the hotkey serves little purpose
    "preset_danger": Item("presetsDanger", BOOLEAN, VAR, None, block=True),

    # Popup Types
    "delay": Item("delay", NONNEGATIVE, VAR, int, danger=Danger(DangerLevel.MEDIUM, Schema(Range(max=1999)))),
    "single_mode": Item("singleMode", BOOLEAN, VAR, bool),
    "image_chance": Item("popupMod", PERCENTAGE, VAR, int),
    "audio_chance": Item("audioMod", PERCENTAGE, VAR, int),
    "max_audio": Item("maxAudio", NONNEGATIVE, VAR, int),
    "audio_volume": Item("audioVolume", PERCENTAGE, VAR, to_float),
    "fade_in_duration": Item("fadeInDuration", NONNEGATIVE, VAR, int),
    "fade_out_duration": Item("fadeOutDuration", NONNEGATIVE, VAR, int),
    "video_chance": Item("vidMod", PERCENTAGE, VAR, int),
    "max_video": Item("maxVideos", NONNEGATIVE, VAR, int),
    "video_volume": Item("videoVolume", PERCENTAGE, VAR, int),
    "web_chance": Item("webMod", PERCENTAGE, VAR, int),
    "web_on_popup_close": Item("webPopup", BOOLEAN, VAR, bool),
    "prompt_chance": Item("promptMod", PERCENTAGE, VAR, int),
    "prompt_max_mistakes": Item("promptMistakes", NONNEGATIVE, VAR, int),
    "subliminal_chance": Item("capPopChance", PERCENTAGE, VAR, int),
    "subliminal_timeout": Item("capPopTimer", NONNEGATIVE, VAR, int),
    "subliminal_opacity": Item("capPopOpacity", PERCENTAGE, VAR, to_float),
    "notification_chance": Item("notificationChance", PERCENTAGE, VAR, int),
    "notification_image_chance": Item("notificationImageChance", PERCENTAGE, VAR, int),

    # Popup Tweaks
    "captions_in_popups": Item("showCaptions", BOOLEAN, VAR, bool),
    "hypno_chance": Item("subliminalsChance", PERCENTAGE, VAR, int),
    "hypno_opacity": Item("subliminalsAlpha", PERCENTAGE, VAR, to_float),
    "denial_chance": Item("denialChance", PERCENTAGE, VAR, int),
    "buttonless": Item("buttonless", BOOLEAN, VAR, bool),
    "multi_click_popups": Item("multiClick", BOOLEAN, VAR, bool),
    "opacity": Item("lkScaling", PERCENTAGE, VAR, to_float),
    "timeout_enabled": Item("timeoutPopups", BOOLEAN, VAR, bool),
    "timeout": Item("popupTimeout", NONNEGATIVE, VAR, s_to_ms),
    "disabled_monitors": Item("disabledMonitors", Schema([str]), None, list, block=True),
    "moving_chance": Item("movingChance", PERCENTAGE, VAR, int),
    "moving_speed": Item("movingSpeed", NONNEGATIVE, VAR, int),
    "clickthrough_enabled": Item("clickthroughPopups", BOOLEAN, VAR, bool),

    # Wallpaper
    "rotate_wallpaper": Item("rotateWallpaper", BOOLEAN, VAR, bool, block=BROKEN),
    "wallpapers": Item("wallpaperDat", STRING, None, lambda value: list(ast.literal_eval(value).values())),
    "wallpaper_timer": Item("wallpaperTimer", NONNEGATIVE, VAR, s_to_ms),
    "wallpaper_variance": Item("wallpaperVariance", NONNEGATIVE, VAR, s_to_ms),

    # Booru
    "booru_download": Item("downloadEnabled", BOOLEAN, VAR, bool),
    "booru_tags": Item("tagList", STRING, None, lambda value: value.replace(">", " ")),
    # "min_score": Item("booruMinScore", Schema(int), VAR, int),  # TODO: Unimplemented

    # Dangerous
    "panic_lockout": Item("timerMode", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.MEDIUM, Schema(1), PANIC_LOCKOUT_DANGER), block=BROKEN),
    "panic_lockout_password": Item("safeword", STRING, VAR, str, block=True),  # imo, the safeword is a safeword for a reason (timer mode)
    "panic_lockout_time": Item("timerSetupTime", NONNEGATIVE, VAR, lambda value: value * 60 * 1000, block=BROKEN),
    "drive_avoid_list": Item("avoidList", STRING, None, lambda value: value.split(">"), block=True),
    "fill_drive": Item("fill", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.MAJOR, Schema(1), FILL_DRIVE_DANGER)),
    "fill_delay": Item("fill_delay", NONNEGATIVE, VAR, lambda value: value * 10),
    "replace_images": Item("replace", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.EXTREME, Schema(1), REPLACE_IMAGES_DANGER), block=BROKEN),
    "replace_threshold": Item("replaceThresh", NONNEGATIVE, VAR, int, block=BROKEN),
    "drive_path": Item("drivePath", STRING, VAR, str, block=True),  # We can't know what paths exist and they look different on Linux and Windows
    "panic_disabled": Item("panicDisabled", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.MINOR, Schema(1), PANIC_DISABLED_DANGER)),
    "run_at_startup": Item("start_on_logon", BOOLEAN, VAR, None, danger=Danger(DangerLevel.MAJOR, Schema(1), RUN_AT_STARTUP_DANGER), block=True),
    "show_on_discord": Item("showDiscord", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.MEDIUM, Schema(1), SHOW_ON_DISCORD_DANGER), block=BROKEN),

    # Modes
    "lowkey_mode": Item("lkToggle", BOOLEAN, VAR, bool),
    "lowkey_corner": Item("lkCorner", Schema(Union(int, Range(min=0, max=4))), VAR, int),
    "mitosis_mode": Item("mitosisMode", BOOLEAN, VAR, bool, danger=Danger(DangerLevel.MEDIUM, Schema(1), MITOSIS_MODE_DANGER), block=BROKEN),
    "mitosis_strength": Item("mitosisStrength", NONNEGATIVE, VAR, int),
    "hibernate_mode": Item("hibernateMode", BOOLEAN, VAR, bool, block=BROKEN),
    "hibernate_type": Item("hibernateType", Schema(Union("Original", "Spaced", "Glitch", "Ramp", "Pump-Scare", "Chaos")), VAR, str),
    "hibernate_delay_min": Item("hibernateMin", NONNEGATIVE, VAR, s_to_ms, danger=Danger(DangerLevel.MEDIUM, Schema(Range(max=29)), HIBERNATE_DELAY_MIN_DANGER)),
    "hibernate_delay_max": Item("hibernateMax", NONNEGATIVE, VAR, s_to_ms, danger=Danger(DangerLevel.MEDIUM, Schema(Range(max=29)), HIBERNATE_DELAY_MAX_DANGER)),
    "hibernate_activity": Item("wakeupActivity", NONNEGATIVE, VAR, int, danger=Danger(DangerLevel.MEDIUM, Schema(Range(min=36)))),
    "hibernate_activity_length": Item("hibernateLength", NONNEGATIVE, VAR, s_to_ms),
    "hibernate_fix_wallpaper": Item("fixWallpaper", BOOLEAN, VAR, bool),

    # Corruption
    "corruption_mode": Item("corruptionMode", BOOLEAN, VAR, bool, block=True),  # if you're turning off corruption mode with corruption just make it the final level lmao
    "corruption_full": Item("corruptionFullPerm", BOOLEAN, VAR, bool, block=True),
    "corruption_trigger": Item("corruptionTrigger", Schema(Union("Timed", "Popup", "Launch", "Script")), VAR, str),
    "corruption_fade": Item("corruptionFadeType", Schema(Union("Normal", "Abrupt")), VAR, str),
    "corruption_time": Item("corruptionTime", NONNEGATIVE, VAR, s_to_ms),
    "corruption_popups": Item("corruptionPopups", NONNEGATIVE, VAR, int),
    "corruption_launches": Item("corruptionLaunches", NONNEGATIVE, VAR, int),
    "corruption_wallpaper": Item("corruptionWallpaperCycle", BOOLEAN, VAR, negation),
    "corruption_themes": Item("corruptionThemeCycle", BOOLEAN, VAR, negation),
    "corruption_purity": Item("corruptionPurityMode", BOOLEAN, VAR, bool),
    "corruption_dev_mode": Item("corruptionDevMode", BOOLEAN, VAR, bool, block=True),

    # Troubleshooting
    "toggle_hibernate_skip": Item("toggleHibSkip", BOOLEAN, VAR, bool, block=True),
    "toggle_mood_set": Item("toggleMoodSet", BOOLEAN, VAR, None, block=True),
    "toggle_internet": Item("toggleInternet", BOOLEAN, VAR, None, block=True),
    "mpv_subprocess": Item("mpvSubprocess", BOOLEAN, VAR, bool, block=True),
    "video_hardware_acceleration": Item("videoHardwareAcceleration", BOOLEAN, VAR, bool),
    "panic_key": Item("panicButton", STRING, VAR, str, block=True),
    "pause_on_lock": Item("pauseOnLock", BOOLEAN, VAR, bool, block=True),

    # Sex toys (Intiface/Buttplug). "sextoys" maps a device-index string to a
    # dict of per-event vibration settings; stored verbatim as JSON. The inner
    # dict is intentionally lenient (just "a dict") so new setting keys can be
    # added without invalidating existing saved devices; the config tab clamps
    # individual values via its sliders.
    "sextoys": Item("sextoys", Schema({str: dict}), VAR, lambda value: value, block=True),
    "intiface_address": Item("intifaceAddress", STRING, VAR, str, block=True),
}
# fmt: on


CONFIG_DANGER: dict[str, Danger] = {
    item.key: item.danger for item in CONFIG_ITEMS.values() if item.danger
}
CORRUPTION_BLOCK: set[str] = {item.key for item in CONFIG_ITEMS.values() if item.block}
