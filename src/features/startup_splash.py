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

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

import utils
from config.settings import Settings
from features.gtk_media import picture_from_pil, stop_media, video_widget
from pack import Pack
from PIL import Image


class StartupSplash(Gtk.Window):
    def __init__(self, settings: Settings, pack: Pack, callback: Callable[[], None]) -> None:
        super().__init__()

        self.callback = callback
        self.opacity = 0.0
        self._media_file = None

        self.set_decorated(False)
        self.set_opacity(0)

        monitor = utils.primary_monitor()

        image = Image.open(pack.startup_splash)

        # Scale splash to ~25% of the shorter monitor dimension
        target = min(monitor.width, monitor.height) * 0.25
        scale = target / max(image.width, image.height)
        width = max(int(image.width * scale), 1)
        height = max(int(image.height * scale), 1)
        self.set_default_size(width, height)

        if getattr(image, "n_frames", 0) > 1:
            video, self._media_file = video_widget(pack.startup_splash, width, height, loop=True, muted=True)
            self.set_child(video)
        else:
            self.set_child(picture_from_pil(image.resize((width, height), Image.LANCZOS), width, height))

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-splash")
            gdk_mon = utils.gdk_monitor_for(monitor)
            if gdk_mon:
                LayerShell.set_monitor(self, gdk_mon)

        self.present()
        self.fade_in()

    def fade_in(self) -> None:
        def step() -> bool:
            self.opacity += 0.02
            if self.opacity >= 1:
                self.set_opacity(1)
                GLib.timeout_add_seconds(2, self.fade_out)
                return GLib.SOURCE_REMOVE
            self.set_opacity(self.opacity)
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(10, step)

    def fade_out(self) -> bool:
        def step() -> bool:
            self.opacity -= 0.02
            if self.opacity <= 0:
                self._finish()
                return GLib.SOURCE_REMOVE
            self.set_opacity(max(0.0, self.opacity))
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(10, step)
        return GLib.SOURCE_REMOVE

    def _finish(self) -> None:
        stop_media(self._media_file)
        self.destroy()
        self.callback()
