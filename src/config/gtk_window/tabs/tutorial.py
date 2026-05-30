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

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

# ---------------------------------------------------------------------------
# Tutorial content — native GTK instead of WebKit/HTML.
# Each entry: (group_title, group_description, [(section_title, body_text)])
# ---------------------------------------------------------------------------

_INTRO = (
    "Welcome",
    "Hello and welcome to Edgeware++ LinuxNative! Read through these sections to learn "
    "how to use the program. Hover over any setting for a tooltip.",
    [
        ("What is Edgeware++?",
         "Edgeware++ is a \"porn delivery service\" that takes images, video, audio and "
         "text from a \"pack\" and places it in popups all over your screen. Creators "
         "make .zip pack files which users import here.\n\n"
         "The idea is to simulate a virus-like program that spams you with content while "
         "you use your computer. You can run it idly in the background or aggressively "
         "front-and-centre. It won't harm your computer unless you explicitly enable the "
         "dangerous settings (Fill Drive, Replace Images) — those are off by default and "
         "clearly marked."),
        ("A note on LinuxNative",
         "This is the Wayland-native fork of Edgeware++. Popups use GTK4 + layer-shell, "
         "media uses GStreamer, and the config window uses libadwaita. X11 and Tkinter "
         "are completely removed.\n\n"
         "The global panic hotkey goes through your compositor's GlobalShortcuts portal "
         "(KDE/GNOME) or the tray icon. On Niri, add a native keybind pointing at "
         "panic.sh — see the Start tab for a ready-to-paste snippet."),
        ("History",
         "Edgeware was created by PetitTournesol in 2021. Araten discovered it in 2023 "
         "and began adding features (originally with zero Python experience). Marigold "
         "joined later and has been invaluable for Linux support, features, organisation "
         "and bugfixing. The LinuxNative fork by sirenondine strips all Windows code and "
         "replaces the runtime with native Wayland APIs."),
    ],
)

_QUICKSTART = (
    "Quick Start",
    "Want to get up and running as fast as possible? Do these three things first.",
    [
        ("1 — Set a panic key",
         "Go to the Start tab and click the Global Panic Key button. Press a key you "
         "won't hit by accident (F9 is a good choice). On Niri, also add the keybind "
         "snippet shown in that tab to ~/.config/niri/config.kdl.\n\n"
         "Panic instantly stops Edgeware and reverts your wallpaper."),
        ("2 — Set a panic wallpaper",
         "Go to Wallpaper → Set Panic Wallpaper. Click \"Auto Import\" to use your "
         "current wallpaper automatically, or pick a file manually.\n\n"
         "Without this, panic will set a blank wallpaper."),
        ("3 — Enable the safety warning",
         "On the Start tab, make sure \"Warn if Dangerous Settings Active\" is on. "
         "It's on by default — this dialog catches you before you accidentally save "
         "destructive settings like Fill Drive or Disable Panic Hotkey."),
        ("Recommended first settings",
         "• Popup Types → Timer Delay: 8000–10000 ms is a gentle start.\n"
         "• Keep Image Popup Chance at 100%.\n"
         "• Videos: ~10%, Subliminals: ~5%, Audio: ~3%, Prompts/Web: 1–2%.\n"
         "• Hit Save & Exit — Edgeware will launch automatically if "
         "\"Run on Save & Exit\" is enabled."),
    ],
)

_GETTING_STARTED = (
    "Getting Started",
    "A guide from the absolute basics — importing a pack and running Edgeware for the first time.",
    [
        ("Importing a pack",
         "Packs are .zip files. Don't extract them — just save the zip somewhere.\n\n"
         "In the config window click \"Import Pack\" in the header bar, then choose:\n\n"
         "• Import New — extracts the pack into data/packs/ so you can switch between "
         "packs instantly with \"Switch Pack\". Recommended if you have several packs.\n\n"
         "• Change Default — overwrites the resource/ folder directly. Use this for "
         "portability or a single-pack setup.\n\n"
         "After importing, the pack name appears in the header subtitle. You can verify "
         "it loaded on the Pack Info tab."),
        ("Running Edgeware",
         "Click Save & Exit in the header (or use Ctrl+S then close) to save and "
         "optionally launch the runtime.\n\n"
         "Scripts in the install folder:\n"
         "• edgeware.sh — starts the runtime\n"
         "• config.sh  — opens this config window\n"
         "• panic.sh   — force-quits the runtime and reverts the wallpaper\n"
         "• setup.sh   — install/update Python dependencies"),
        ("Stopping Edgeware",
         "• Press your global panic key (set on the Start tab).\n"
         "• Click Panic in the system tray menu.\n"
         "• Click \"Perform Panic\" on the Start tab.\n"
         "• Run panic.sh from a terminal.\n\n"
         "All methods send a message over a Unix socket — they work even if the "
         "compositor's GlobalShortcuts portal is unavailable."),
    ],
)

_SETTINGS_101 = (
    "Settings 101",
    "A tour of the most important tabs and the settings you'll actually use.",
    [
        ("Start",
         "Meta-settings for the program itself: panic key, loading splash, desktop icon "
         "shortcuts, the safety warning, config presets, and the pack config loader.\n\n"
         "Always set your panic key here before running Edgeware."),
        ("Popup Types",
         "Controls what kinds of popups appear and how often.\n\n"
         "Timer Delay is the master pacing knob — lower = faster. Single Popup Per Roll "
         "makes each tick pick one type instead of rolling each independently.\n\n"
         "Each type has a chance slider. Set types you don't want to 0%."),
        ("Popup Tweaks",
         "Fine-tunes popup appearance and behaviour: captions, hypno/denial overlays, "
         "opacity, timeout (auto-close), buttonless mode, multi-click, per-monitor "
         "on/off, and popup movement (drift)."),
        ("Wallpaper",
         "Set a panic wallpaper (critical!) and optionally cycle through a list of "
         "rotating wallpapers during a session. Timers and variance control rotation speed."),
        ("Moods",
         "Each media file in a pack is tagged with a mood. Toggle moods on/off here to "
         "filter what content appears. Use Select All / Deselect All for bulk changes."),
        ("Modes",
         "Lowkey: pins popups to one corner.\n"
         "Mitosis: closing a popup spawns more.\n"
         "Hibernate: Edgeware runs invisibly then bursts — choose the burst style "
         "(Original, Spaced, Glitch, Ramp, Pump-Scare, Chaos)."),
        ("Corruption",
         "A pack-level feature: moods are toggled on/off as you hit trigger thresholds "
         "(time, popup count, or launch count). The pack must explicitly support it — "
         "check the Pack Info tab for the Corruption status indicator."),
        ("Dangerous",
         "Panic Lockout, Fill Drive, Replace Images, folder blacklist. "
         "These are intentionally hard to reach. Enable the safe-mode warning on the "
         "Start tab so you get a confirmation dialog before saving if any of these are on."),
    ],
)

_HIBERNATE_TYPES = (
    "Hibernate Types",
    "Reference for what each hibernate burst type does when Edgeware wakes up.",
    [
        ("Original",
         "Spawns an immediate burst of popups on wakeup. The number is controlled by "
         "the Awaken Activity slider."),
        ("Spaced",
         "Runs Edgeware normally (using the popup delay) over the activity length, "
         "creating popups at the regular interval instead of all at once."),
        ("Glitch",
         "Creates popups at random times distributed over the activity length, "
         "giving an unpredictable, glitchy feeling."),
        ("Ramp",
         "Popup frequency starts slow and increases over the activity length — "
         "a gradual build-up."),
        ("Pump-Scare",
         "A single popup with audio appears very briefly then disappears — "
         "a jump-scare style interruption."),
        ("Chaos",
         "Each time hibernate activates, one of the other types is chosen at random."),
    ],
)


def _section_group(group_title: str, group_desc: str, sections: list) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=group_title, description=group_desc)
    for title, body in sections:
        expander = Adw.ExpanderRow(title=title)
        text_row = Adw.ActionRow()
        text_row.set_activatable(False)

        lbl = Gtk.Label(label=body, wrap=True, xalign=0)
        lbl.set_margin_start(12)
        lbl.set_margin_end(12)
        lbl.set_margin_top(8)
        lbl.set_margin_bottom(8)
        text_row.set_child(lbl)
        expander.add_row(text_row)
        group.add(expander)
    return group


class TutorialTab(Adw.PreferencesPage):
    def __init__(self) -> None:
        super().__init__()
        for args in [_INTRO, _QUICKSTART, _GETTING_STARTED, _SETTINGS_101, _HIBERNATE_TYPES]:
            self.add(_section_group(*args))
