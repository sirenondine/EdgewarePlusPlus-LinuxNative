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

from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import GdkPixbuf, Gtk

from config.gtk_window.widgets import PAD, ConfigSection
from paths import CustomAssets, Data

INTRO_TEXT = (
    "Changing these will change the default file Edgeware++ falls back on when a replacement "
    "isn't provided by a pack. The files you choose will be stored under \"data\"."
)


class DefaultFileTab(Gtk.ScrolledWindow):
    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        section = ConfigSection("Default Files", INTRO_TEXT)
        vbox.append(section)

        row_1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        section.append(row_1)
        row_1.append(
            _DefaultImageFrame(
                CustomAssets.startup_splash(),
                Data.STARTUP_SPLASH,
                (150, 150),
                "Default Loading Splash",
                "LOADING SPLASH:\n\nUsed in \"Show Loading Flair\" setting (found in \"Start\" tab).",
            )
        )
        row_1.append(
            _DefaultImageFrame(
                CustomAssets.theme_demo(),
                Data.THEME_DEMO,
                (150, 75),
                "Theme Demo",
                "THEME DEMO:\n\nUsed in the \"Start\" tab. Must be 150x75!",
            )
        )

        row_2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        section.append(row_2)
        row_2.append(
            _DefaultImageFrame(
                CustomAssets.icon(),
                Data.ICON,
                (70, 70),
                "Icon",
                "ICON:\n\nUsed in desktop shortcuts and tray icon. Only supports .ico files.",
            )
        )
        row_2.append(
            _DefaultImageFrame(
                CustomAssets.config_icon(),
                Data.CONFIG_ICON,
                (70, 70),
                "Config Icon",
                "CONFIG ICON:\n\nUsed in desktop shortcuts and the config window. Only supports .ico files.",
            )
        )
        row_2.append(
            _DefaultImageFrame(
                CustomAssets.panic_icon(),
                Data.PANIC_ICON,
                (70, 70),
                "Panic Icon",
                "PANIC ICON:\n\nUsed in desktop shortcuts. Only supports .ico files.",
            )
        )

        row_3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        section.append(row_3)
        row_3.append(
            _DefaultImageFrame(
                CustomAssets.hypno(),
                Data.HYPNO,
                (200, 200),
                "Default Hypno",
                "HYPNO:\n\nUsed in \"Hypno Overlays\" setting (found in \"Popup Tweaks\" tab).",
            )
        )


class _DefaultImageFrame(Gtk.Frame):
    def __init__(
        self,
        image_file: Path,
        custom_file: Path,
        size: tuple[int, int],
        title: str,
        message: str,
    ) -> None:
        super().__init__()
        self._custom_file = custom_file
        self._size = size

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=PAD)
        self.set_child(hbox)

        col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hbox.append(col1)

        btn = Gtk.Button(label=f"Change {title}")
        btn.connect("clicked", self._on_change)
        col1.append(btn)

        info = Gtk.Label(label=message, wrap=True)
        col1.append(info)

        col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hbox.append(col2)

        title_lbl = Gtk.Label(label=title)
        col2.append(title_lbl)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(image_file), size[0], size[1])
            image = Gtk.Picture.new_for_pixbuf(pixbuf)
        except Exception:
            image = Gtk.Picture()
            image.set_size_request(size[0], size[1])
        col2.append(image)
        self._image = image

    def _on_change(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Choose Image")
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        filt.add_mime_type("image/gif")
        fd.set_default_filter(filt)
        fd.open(None, self._on_file_selected, None)

    def _on_file_selected(self, fd: Gtk.FileDialog, result, _ud) -> None:
        try:
            file = fd.open_finish(result)
            if not file:
                return
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(file.get_path(), self._size[0], self._size[1])
            self._image.set_pixbuf(pixbuf)
        except Exception:
            pass
