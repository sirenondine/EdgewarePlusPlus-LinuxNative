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

import logging
import shutil
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GdkPixbuf, Gtk

from pack import Pack
from paths import CustomAssets, Data


class DefaultFileTab(Adw.PreferencesPage):
    def __init__(self, pack: Pack) -> None:
        super().__init__()
        self._pack = pack

        # ---- Default fallback files (global, stored under data/) ----------
        defaults = Adw.PreferencesGroup(
            title="Default Fallback Files",
            description="Used when the loaded pack doesn't provide its own. Stored under \"data\".",
        )
        self.add(defaults)

        defaults.add(_FileRow(
            "Loading Splash", "Shown by the \"Show Loading Flair\" setting (Start tab).",
            CustomAssets.startup_splash(), Data.STARTUP_SPLASH))
        defaults.add(_FileRow(
            "Theme Demo", "Preview shown on the Start tab. Should be 150×75.",
            CustomAssets.theme_demo(), Data.THEME_DEMO))
        defaults.add(_FileRow(
            "App Icon", "Desktop shortcuts and the tray icon. .ico only.",
            CustomAssets.icon(), Data.ICON, ico=True))
        defaults.add(_FileRow(
            "Config Icon", "Desktop shortcut and the config window. .ico only.",
            CustomAssets.config_icon(), Data.CONFIG_ICON, ico=True))
        defaults.add(_FileRow(
            "Panic Icon", "Panic desktop shortcut. .ico only.",
            CustomAssets.panic_icon(), Data.PANIC_ICON, ico=True))
        defaults.add(_FileRow(
            "Hypno Overlay", "Used by the \"Hypno Overlays\" setting (Popup Tweaks tab).",
            CustomAssets.hypno(), Data.HYPNO))

        # ---- Current pack files (write into the loaded pack) --------------
        pack_group = Adw.PreferencesGroup(
            title=f"Current Pack Files — {pack.info.name}",
            description="Replace the branding files inside the pack that's loaded now.",
        )
        self.add(pack_group)

        root = pack.paths.root
        pack_group.add(_FileRow(
            "Pack Icon", "icon.ico in the pack.",
            pack.paths.icon, root / "icon.ico", ico=True))
        pack_group.add(_FileRow(
            "Pack Loading Splash", "loading_splash.png in the pack.",
            next((p for p in pack.paths.splash if p.is_file()), root / "loading_splash.png"),
            root / "loading_splash.png"))
        pack_group.add(_FileRow(
            "Pack Wallpaper", "wallpaper.png in the pack.",
            pack.paths.wallpaper, root / "wallpaper.png"))


class _FileRow(Adw.ActionRow):
    """One file: thumbnail preview + a Change button that actually saves it."""

    def __init__(self, title: str, subtitle: str, current: Path, dest: Path, ico: bool = False) -> None:
        super().__init__(title=title, subtitle=subtitle)
        self._dest = dest
        self._ico = ico

        self._image = Gtk.Picture()
        self._image.set_size_request(64, 48)
        self._image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._image.set_can_shrink(True)
        self._load_preview(current)

        frame = Gtk.Frame()
        frame.set_valign(Gtk.Align.CENTER)
        frame.add_css_class("card")
        frame.set_child(self._image)
        self.add_prefix(frame)

        button = Gtk.Button(label="Change…")
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", self._on_change)
        self.add_suffix(button)
        self.set_activatable_widget(button)

    def _load_preview(self, path: Path) -> None:
        # Gtk.Picture.set_filename relies on GDK's built-in loaders which don't
        # handle .ico or .gif. Fall back to GdkPixbuf (which has those loaders)
        # and hand it in as a pixbuf, scaled to fit the 64×48 preview area.
        if not path or not path.is_file():
            self._image.set_paintable(None)
            return
        suffix = path.suffix.lower()
        if suffix in (".ico", ".gif"):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 64, 48, True)
                self._image.set_pixbuf(pb)
            except Exception:
                self._image.set_paintable(None)
        else:
            try:
                self._image.set_filename(str(path))
            except Exception:
                self._image.set_paintable(None)

    def _on_change(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title(f"Choose {self.get_title()}")
        filt = Gtk.FileFilter()
        if self._ico:
            filt.set_name("Icon files")
            filt.add_pattern("*.ico")
        else:
            filt.set_name("Image files")
            for mime in ("image/png", "image/jpeg", "image/gif", "image/bmp"):
                filt.add_mime_type(mime)
        fd.set_default_filter(filt)
        fd.open(self.get_root(), None, self._on_selected, None)

    def _on_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        try:
            file = fd.open_finish(result)
        except Exception:
            return
        if not file:
            return
        src = Path(file.get_path())
        try:
            self._dest.parent.mkdir(parents=True, exist_ok=True)
            if self._ico and src.suffix.lower() != ".ico":
                from PIL import Image
                Image.open(src).save(self._dest)  # convert to .ico
            else:
                shutil.copyfile(src, self._dest)
            self._load_preview(self._dest)
            from config.gtk_window.toast import toast
            toast(f"{self.get_title()} updated.")
        except Exception as e:
            logging.warning(f"Failed to set {self.get_title()}: {e}")
            from config.gtk_window.toast import toast
            toast(f"Couldn't update {self.get_title()}.")
