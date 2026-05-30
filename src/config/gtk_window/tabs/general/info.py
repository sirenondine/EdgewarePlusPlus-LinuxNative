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
from gi.repository import Adw, GLib, Gtk

from pack import Pack

MULTI_PACK_TEXT = (
    "If you have multiple packs loaded, make sure to apply the one you want using "
    "\"Switch Pack\" at the bottom of the window."
)
INFO_TEXT = (
    "Requires an optional \"information file\" that pack creators can add. If this is "
    "greyed out but other sections work, the pack just doesn't have one."
)
DISCORD_TEXT = (
    "Only displays on Discord if you turn on the associated \"Show on Discord\" "
    "setting (Dangerous Settings tab)."
)


class InfoTab(Adw.PreferencesPage):
    def __init__(self, pack: Pack) -> None:
        super().__init__()

        # ---- Status ------------------------------------------------------
        status = Adw.PreferencesGroup(title="Pack Status", description=MULTI_PACK_TEXT)
        self.add(status)
        status.add(_status_row("Pack Loaded", pack.paths.root.exists()))
        status.add(_status_row("Info File", pack.paths.info.is_file()))
        status.add(_status_row("Wallpaper", pack.paths.wallpaper.is_file()))
        status.add(_status_row(
            "Custom Startup", bool(pack.paths.splash),
            "For older packs, put the file in /resource/ named \"loading_splash.png\"."))
        status.add(_status_row("Custom Discord Status", pack.paths.discord.is_file()))
        status.add(_status_row(
            "Custom Icon", pack.paths.icon.is_file(),
            "Put the file in /resource/ named \"icon.ico\"."))
        status.add(_status_row(
            "Corruption", pack.paths.corruption.is_file(),
            "An Edgeware++ feature that changes content over time."))

        # ---- Content counts ----------------------------------------------
        content = Adw.PreferencesGroup(title="Content")
        self.add(content)
        content.add(_count_row("Images", len(pack.images)))
        content.add(_count_row("Audio Files", len(pack.audio)))
        content.add(_count_row("Videos", len(pack.videos)))
        content.add(_count_row("Web Links", _list_length(pack, "web")))
        content.add(_count_row("Prompts", _list_length(pack, "prompts")))
        content.add(_count_row("Captions", _list_length(pack, "captions")))
        content.add(_count_row("Hypnos", len(pack.hypnos)))

        # ---- Information -------------------------------------------------
        has_info = pack.paths.info.is_file()
        info = Adw.PreferencesGroup(title="Information", description=INFO_TEXT)
        info.set_sensitive(has_info)
        self.add(info)
        info.add(_value_row("Pack Name", pack.info.name))
        info.add(_value_row("Author Name", pack.info.creator))
        info.add(_value_row("Version", pack.info.version))
        desc_row = Adw.ActionRow(title="Description")
        desc_row.set_subtitle(GLib.markup_escape_text(pack.info.description or ""))
        info.add(desc_row)

        # ---- Discord -----------------------------------------------------
        discord = Adw.PreferencesGroup(title="Discord Information", description=DISCORD_TEXT)
        discord.set_sensitive(pack.paths.discord.is_file())
        self.add(discord)
        status_row = Adw.ActionRow(title="Custom Discord Status")
        status_row.set_subtitle(GLib.markup_escape_text(pack.discord.text or ""))
        discord.add(status_row)
        image_row = Adw.ActionRow(title="Discord Status Image")
        image_row.add_suffix(_value_label(pack.discord.image))
        image_row.set_tooltip_text(
            "The image is fetched from the Discord application API, which can't be "
            "accessed without permissions, so it can't be previewed here."
        )
        discord.add(image_row)


def _status_row(title: str, ok: bool, tooltip: str | None = None) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    if tooltip:
        row.set_tooltip_text(tooltip)
    lbl = Gtk.Label(label="✓" if ok else "✗")
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.add_css_class("status-ok" if ok else "status-fail")
    row.add_suffix(lbl)
    return row


def _count_row(title: str, number: int) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    lbl = Gtk.Label(label=str(number))
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.add_css_class("stats-number")
    row.add_suffix(lbl)
    return row


def _value_row(title: str, value: str) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    row.add_suffix(_value_label(value))
    return row


def _value_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text or "")
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.set_wrap(True)
    lbl.add_css_class("dim-label")
    return lbl


def _list_length(pack: Pack, attr: str) -> int:
    return len(getattr(pack.index.default, attr)) + sum(
        [len(getattr(mood, attr)) for mood in pack.index.moods]
    )
