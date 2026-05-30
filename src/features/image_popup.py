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
from pathlib import Path
from random import randint
from threading import Thread
from typing import Callable

from gi.repository import GLib, Gtk

import utils
from config.settings import Settings
from features.gtk_media import pil_to_pixbuf, stop_media, video_widget
from features.popup import Popup
from pack import Pack
from PIL import Image
from roll import roll
from state import State


class ImagePopup(Popup):
    vibration_open_event = "image_open"
    vibration_close_event = "image_close"
    vibration_continuous_key = "image"

    def __init__(self, settings: Settings, pack: Pack, state: State, media: Path | None = None, on_close: Callable[[], None] | None = None) -> None:
        self.media = media or pack.random_image()
        self.hypno = roll(settings.hypno_chance)
        if not self.should_init(settings, state):
            return
        super().__init__(settings, pack, state, on_close)

        self._media_file = None
        # Pick the monitor on the main thread (GDK / screeninfo are not
        # thread-safe). Everything expensive — the optional booru network
        # fetch, decode and resize — runs on a worker thread so it never
        # hitches the main loop; the widget is built + presented back on main.
        self.monitor = utils.random_monitor(settings)
        denial_filter = self.try_denial_filter()
        Thread(target=self._prepare, args=(denial_filter,), daemon=True).start()

    def _acquire_image(self) -> Image.Image:
        """Worker-thread image source: booru network fetch (when enabled) or the
        local pack image. Network I/O must stay off the main thread."""
        # TODO: Better booru integration
        if self.settings.booru_download and roll(50):
            try:
                # Deferred: booru pulls in bs4 + aiohttp + lxml (~135ms) — keep it
                # off the startup path since downloads are off by default.
                import asyncio
                import booru
                import requests
                gel = booru.Gelbooru()
                result = booru.resolve(asyncio.run(gel.search_image(query=self.settings.booru_tags, limit=1)))
                data = requests.get(result[0], stream=True)
                return Image.open(data.raw)
            except Exception:
                logging.error(f'No results for tags "{self.settings.booru_tags}" on Gelbooru')
        return Image.open(self.media)

    def _prepare(self, denial_filter) -> None:
        try:
            image = self._acquire_image()
            src_w, src_h = image.width, image.height
            if getattr(image, "n_frames", 0) > 1:
                # Animated — must build the GStreamer widget on the main thread.
                GLib.idle_add(self._finish_animated, src_w, src_h)
                return
            # Geometry is pure math now that the monitor is already chosen.
            self.compute_geometry(src_w, src_h)
            # draft() lets the JPEG loader decode at a reduced scale near the
            # target (big win for multi-megapixel sources); no-op for PNG/GIF.
            try:
                image.draft(None, (self.width, self.height))
            except Exception:
                pass
            resized = image.resize((self.width, self.height), Image.LANCZOS).convert("RGBA")
            if denial_filter == "resizeblur":
                shrink_d = randint(5, 15)
                resized = resized.resize((int(self.width / shrink_d), int(self.height / shrink_d)), Image.BILINEAR)
                resized = resized.resize((self.width, self.height), Image.NEAREST)
                denial_filter = ""
            final = resized.filter(denial_filter) if denial_filter else resized
            pixbuf = pil_to_pixbuf(final)
        except Exception as e:
            logging.warning(f"image popup prepare failed: {e}")
            GLib.idle_add(self.close)  # release the slot + destroy the empty window
            return
        GLib.idle_add(self._finish_still, pixbuf)

    def _finish_animated(self, src_w: int, src_h: int) -> bool:
        self.compute_geometry(src_w, src_h)
        video, self._media_file = video_widget(self.media, self.width, self.height, loop=True, muted=True, blur=self.denial, hardware_acceleration=self.settings.video_hardware_acceleration)
        self.set_media_widget(video)
        self.init_finish()
        return False

    def _finish_still(self, pixbuf) -> bool:
        picture = Gtk.Picture.new_for_pixbuf(pixbuf)
        picture.set_size_request(self.width, self.height)
        picture.set_content_fit(Gtk.ContentFit.FILL)

        if self.hypno:
            overlay = Gtk.Overlay()
            overlay.set_child(picture)
            hypno_video, self._media_file = video_widget(self.pack.random_hypno(), self.width, self.height, loop=True, muted=True)
            hypno_video.set_opacity(self.settings.hypno_opacity)
            overlay.add_overlay(hypno_video)
            self.set_media_widget(overlay)
        else:
            self.set_media_widget(picture)

        self.init_finish()
        return False

    def should_init(self, settings: Settings, state: State) -> bool:
        if self.media and state.image_number < settings.max_image:
            state.image_number += 1
            return True
        return False

    def close(self) -> None:
        stop_media(self._media_file)
        super().close()
        self.state.image_number -= 1
