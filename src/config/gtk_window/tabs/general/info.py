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

import os

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from pack import Pack
from paths import Data

INFO_TEXT = (
    "Requires an optional \"information file\" that pack creators can add. If this is "
    "greyed out but other sections work, the pack just doesn't have one."
)
DISCORD_TEXT = (
    "Only displays on Discord if you turn on the associated \"Show on Discord\" "
    "setting (Dangerous Settings tab)."
)


class InfoTab(Adw.PreferencesPage):
    def __init__(self, pack: Pack, vars=None) -> None:
        super().__init__()
        self._pack = pack
        self._vars = vars

        # ---- Pack management ---------------------------------------------
        mgmt = Adw.PreferencesGroup(title="Pack Management")
        self.add(mgmt)

        current_row = Adw.ActionRow(
            title="Active Pack",
            subtitle=pack.info.name,
        )
        current_row.add_suffix(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        mgmt.add(current_row)

        import_row = Adw.ActionRow(
            title="Import New Pack",
            subtitle="Copy a .zip pack into data/packs/ for easy switching.",
        )
        import_btn = Gtk.Button(label="Import…")
        import_btn.set_valign(Gtk.Align.CENTER)
        import_btn.connect("clicked", lambda _: self._on_import_new())
        import_row.add_suffix(import_btn)
        import_row.set_activatable_widget(import_btn)
        mgmt.add(import_row)

        change_row = Adw.ActionRow(
            title="Change Default Pack",
            subtitle="Overwrites resource/ — use Import New for multi-pack setups.",
        )
        change_btn = Gtk.Button(label="Choose…")
        change_btn.set_valign(Gtk.Align.CENTER)
        change_btn.connect("clicked", lambda _: self._on_change_default())
        change_row.add_suffix(change_btn)
        change_row.set_activatable_widget(change_btn)
        mgmt.add(change_row)

        # Switch pack list
        pack_list = sorted(os.listdir(Data.PACKS)) if Data.PACKS.exists() else []
        if pack_list:
            switch_group = Adw.PreferencesGroup(
                title="Installed Packs",
                description="Click a pack to switch to it. Changes save automatically.",
            )
            self.add(switch_group)

            current_name = vars.pack_path.get() if vars else ""
            for name in pack_list:
                row = Adw.ActionRow(title=name)
                if name == current_name:
                    check = Gtk.Image.new_from_icon_name("object-select-symbolic")
                    check.add_css_class("accent")
                    check.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(check)
                else:
                    sw_btn = Gtk.Button(label="Switch")
                    sw_btn.set_valign(Gtk.Align.CENTER)
                    sw_btn.connect("clicked", lambda _b, n=name: self._on_switch(n))
                    row.add_suffix(sw_btn)
                    row.set_activatable_widget(sw_btn)
                switch_group.add(row)

            default_row = Adw.ActionRow(
                title="Default Pack",
                subtitle="The built-in resource/ pack.",
            )
            def_btn = Gtk.Button(label="Switch")
            def_btn.set_valign(Gtk.Align.CENTER)
            def_btn.connect("clicked", lambda _: self._on_switch("default"))
            default_row.add_suffix(def_btn)
            default_row.set_activatable_widget(def_btn)
            switch_group.add(default_row)

        # ---- Status ------------------------------------------------------
        status = Adw.PreferencesGroup(title="Pack Status")
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
        image_row.set_subtitle(GLib.markup_escape_text(pack.discord.image or ""))
        image_row.set_tooltip_text(
            "The image is fetched from the Discord application API, which can't be "
            "accessed without permissions, so it can't be previewed here."
        )
        discord.add(image_row)


    def _on_import_new(self) -> None:
        from config.gtk_window.import_pack import import_pack
        import_pack(False)

    def _on_change_default(self) -> None:
        from config.gtk_window.import_pack import import_pack
        import_pack(True)

    def _on_switch(self, name: str) -> None:
        if self._vars:
            from config.gtk_window.utils import write_save, refresh
            self._vars.pack_path.set(name)
            write_save(self._vars)
            refresh()


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
    row.set_subtitle(GLib.markup_escape_text(value or ""))
    return row


def _list_length(pack: Pack, attr: str) -> int:
    return len(getattr(pack.index.default, attr)) + sum(
        [len(getattr(mood, attr)) for mood in pack.index.moods]
    )
