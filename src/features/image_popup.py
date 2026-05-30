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
from typing import Callable

from gi.repository import Gtk

from config.settings import Settings
from features.gtk_media import picture_from_pil, stop_media, video_widget
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
        if not self.should_init():
            return
        super().__init__(settings, pack, state, on_close)

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
                image = Image.open(data.raw)
            except Exception:
                logging.error(f'No results for tags "{self.settings.booru_tags}" on Gelbooru')
                image = Image.open(self.media)
        else:
            image = Image.open(self.media)
        self.compute_geometry(image.width, image.height)

        self._media_file = None

        if getattr(image, "n_frames", 0) > 1:
            # Animated image — play natively via GStreamer
            video, self._media_file = video_widget(self.media, self.width, self.height, loop=True, muted=True, blur=self.denial, hardware_acceleration=self.settings.video_hardware_acceleration)
            self.set_media_widget(video)
        else:
            resized = image.resize((self.width, self.height), Image.LANCZOS).convert("RGBA")
            filter = self.try_denial_filter()
            if filter == "resizeblur":
                shrink_d = randint(5, 15)
                resized = resized.resize((int(self.width / shrink_d), int(self.height / shrink_d)), Image.BILINEAR)
                resized = resized.resize((self.width, self.height), Image.NEAREST)
                filter = ""
            final = resized.filter(filter) if filter else resized

            if self.hypno:
                # Static image with an animated hypno overlay on top
                overlay = Gtk.Overlay()
                overlay.set_child(picture_from_pil(final, self.width, self.height))
                hypno_video, self._media_file = video_widget(self.pack.random_hypno(), self.width, self.height, loop=True, muted=True)
                hypno_video.set_opacity(self.settings.hypno_opacity)
                overlay.add_overlay(hypno_video)
                self.set_media_widget(overlay)
            else:
                self.set_media_widget(picture_from_pil(final, self.width, self.height))

        self.init_finish()

    def should_init(self) -> bool:
        return self.media

    def close(self) -> None:
        stop_media(self._media_file)
        super().close()
