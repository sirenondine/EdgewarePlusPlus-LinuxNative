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

import json
import os
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GdkPixbuf, GLib, Gtk

from pack import Pack
from paths import Data

INFO_TEXT = (
    "Requires an optional \"information file\" that pack creators can add. If this is "
    "greyed out but other sections work, the pack just doesn't have one."
)
DISCORD_TEXT = (
    "Only displays on Discord if you turn on the associated \"Show on Discord\" "
    "setting (Dangerous)."
)


class InfoTab(Adw.PreferencesPage):
    def __init__(self, pack: Pack, vars=None, on_switch_pack=None) -> None:
        super().__init__()
        self._pack = pack
        self._vars = vars
        self._on_switch_pack = on_switch_pack

        # ---- Pack management ---------------------------------------------
        mgmt = Adw.PreferencesGroup(title="Pack Management")
        self.add(mgmt)

        current_row = Adw.ActionRow(title="Active Pack", subtitle=pack.info.name)
        current_row.add_prefix(_pack_icon_prefix(pack.paths.root))
        current_row.add_suffix(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        mgmt.add(current_row)

        import_row = Adw.ActionRow(
            title="Import New Pack",
            subtitle="Extract a .zip into data/packs/ for easy switching.",
        )
        import_btn = Gtk.Button()
        import_btn.set_child(Adw.ButtonContent(label="Import…", icon_name="folder-download-symbolic"))
        import_btn.set_valign(Gtk.Align.CENTER)
        import_btn.connect("clicked", lambda _: self._on_import_new())
        import_row.add_suffix(import_btn)
        import_row.set_activatable_widget(import_btn)
        mgmt.add(import_row)

        # ---- Pack configuration (this pack's creator-suggested settings) ---
        if vars is not None:
            from config.gtk_window.preset import apply_preset
            from config.gtk_window.widgets import AdwSwitchRow

            config_group = Adw.PreferencesGroup(
                title="Pack Configuration",
                description=(
                    "Pack creators can ship a config file with settings tailored to "
                    "their intended experience for this pack."
                ),
            )
            self.add(config_group)

            load_cfg_row = Adw.ActionRow(
                title="Load Pack Configuration",
                subtitle=f"{len(pack.config)} suggested setting"
                         f"{'s' if len(pack.config) != 1 else ''} in this pack.",
            )
            load_cfg_btn = Gtk.Button(label="Load")
            load_cfg_btn.set_valign(Gtk.Align.CENTER)
            load_cfg_btn.set_sensitive(bool(pack.config))
            load_cfg_btn.connect("clicked", lambda _: apply_preset(pack.config, vars))
            load_cfg_row.add_suffix(load_cfg_btn)
            load_cfg_row.set_activatable_widget(load_cfg_btn)
            config_group.add(load_cfg_row)

            config_group.add(AdwSwitchRow(
                "Force Warning Failsafes", vars.preset_danger,
                subtitle=(
                    "Turns on \"Warn if Dangerous Settings Active\" after loading a pack "
                    "config, regardless of the config's own setting."
                )))

        # ---- Installed packs ----------------------------------------------
        pack_dirs = sorted(
            [d for d in Data.PACKS.iterdir() if d.is_dir()],
            key=lambda d: d.name.lower()
        ) if Data.PACKS.exists() else []

        if pack_dirs:
            from config.gtk_window.import_pack import get_default_pack_source
            switch_group = Adw.PreferencesGroup(
                title="Installed Packs",
                description="Switch activates the pack. Set Default copies it to resource/.",
            )
            self.add(switch_group)

            current_name = vars.pack_path.get() if vars else ""
            self._default_buttons: dict[str, Gtk.Button] = {}  # dir name → star button

            default_source = get_default_pack_source()

            for pack_dir in pack_dirs:
                name = pack_dir.name
                info = _read_pack_info(pack_dir)
                display_name = info.get("name") or name
                description = info.get("description") or ""

                row = Adw.ActionRow(title=display_name)
                if description:
                    row.set_subtitle(GLib.markup_escape_text(description[:120]))
                row.add_prefix(_pack_icon_prefix(pack_dir))

                btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                btn_box.set_valign(Gtk.Align.CENTER)

                if name == current_name:
                    check = Gtk.Image.new_from_icon_name("object-select-symbolic")
                    check.add_css_class("accent")
                    check.set_valign(Gtk.Align.CENTER)
                    btn_box.append(check)
                else:
                    sw_btn = Gtk.Button(label="Switch")
                    sw_btn.connect("clicked", lambda _b, n=name: self._on_switch(n))
                    btn_box.append(sw_btn)

                # Star button: filled+accent when this is the default pack,
                # outline otherwise. Clicking sets this pack as default.
                set_def_btn = Gtk.Button()
                set_def_btn.connect("clicked", lambda _b, d=pack_dir: self._on_set_default(d))
                btn_box.append(set_def_btn)
                self._default_buttons[name] = set_def_btn
                self._style_default_button(set_def_btn, name == default_source)

                row.add_suffix(btn_box)
                switch_group.add(row)

            default_row = Adw.ActionRow(
                title="Default Pack",
                subtitle="The built-in resource/ pack — no switch needed.",
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

    @staticmethod
    def _style_default_button(btn: Gtk.Button, is_default: bool) -> None:
        if is_default:
            btn.set_icon_name("starred-symbolic")
            btn.add_css_class("accent")
            btn.set_tooltip_text("This is the default pack")
        else:
            btn.set_icon_name("non-starred-symbolic")
            btn.remove_css_class("accent")
            btn.set_tooltip_text("Set as default pack (copies to resource/)")

    def _on_set_default(self, pack_dir) -> None:
        from config.gtk_window.import_pack import set_default_from_installed

        def on_done(new_default: str) -> None:
            for name, btn in self._default_buttons.items():
                self._style_default_button(btn, name == new_default)

        set_default_from_installed(pack_dir, on_done=on_done)

    def _on_switch(self, name: str) -> None:
        if self._on_switch_pack:
            self._on_switch_pack(name)


def _pack_icon_prefix(pack_dir: Path) -> Gtk.Widget:
    """32×32 pack icon framed for use as an ActionRow prefix."""
    SIZE = 32
    picture = Gtk.Picture()
    picture.set_size_request(SIZE, SIZE)
    picture.set_content_fit(Gtk.ContentFit.COVER)
    picture.set_can_shrink(True)

    icon_path = pack_dir / "icon.ico"
    loaded = False
    if icon_path.is_file():
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), SIZE, SIZE, True)
            picture.set_pixbuf(pb)
            loaded = True
        except Exception:
            pass

    if not loaded:
        # Fall back to a generic app icon
        from paths import CustomAssets
        fallback = CustomAssets.icon()
        if fallback.is_file():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(fallback), SIZE, SIZE, True)
                picture.set_pixbuf(pb)
            except Exception:
                pass

    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_valign(Gtk.Align.CENTER)
    frame.set_size_request(SIZE, SIZE)
    frame.set_child(picture)
    return frame


def _read_pack_info(pack_dir: Path) -> dict:
    """Cheaply read name/description from info.json without loading the full Pack."""
    for candidate in ("info.json", "resource/info.json"):
        p = pack_dir / candidate
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


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
