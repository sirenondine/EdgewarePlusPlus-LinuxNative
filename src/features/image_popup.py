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
from PIL import Image

import utils
from config.settings import Settings
from features.gtk_media import pil_to_pixbuf, stop_media, video_widget
from features.popup import Popup
from pack import Pack
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
        self._booru_tmp = None  # temp file for downloaded booru media, cleaned on close
        self._booru_post_url = None  # link back to the booru post page, if any
        # Pick the monitor on the main thread (GDK / screeninfo are not
        # thread-safe). Everything expensive — the optional booru network
        # fetch, decode and resize — runs on a worker thread so it never
        # hitches the main loop; the widget is built + presented back on main.
        self.monitor = utils.random_monitor(settings)
        # The censor path (features.censor) handles any non-blur style, ML region
        # detection, or in-image captions. Plain blur with none of those keeps the
        # original lightweight denial-filter path for backward compatibility.
        style = settings.denial_style
        self._use_censor = self.denial and (style != "blur" or settings.denial_detect or settings.denial_caption_in_image)
        denial_filter = "" if self._use_censor else self.try_denial_filter()
        Thread(target=self._prepare, args=(denial_filter,), daemon=True).start()

    def _acquire_source(self):
        """Worker-thread media source: a booru network fetch (when enabled),
        downloaded to a temp file, else the local pack image. Network I/O must
        stay off the main thread. Returns a filesystem path."""
        if self.settings.booru_download and roll(self.settings.booru_chance):
            try:
                import os
                import tempfile

                from features import booru

                site = getattr(self.settings, "booru_site", "gelbooru")
                custom_url = getattr(self.settings, "booru_custom_url", "") or ""
                api_type = getattr(self.settings, "booru_api_type", "danbooru") or "danbooru"
                post = booru.random_media(
                    site,
                    self.settings.booru_tags,
                    api_key=getattr(self.settings, "booru_api_key", "") or "",
                    user_id=getattr(self.settings, "booru_user_id", "") or "",
                    exclude=getattr(self.settings, "booru_exclude", "") or "",
                    rating=getattr(self.settings, "booru_rating", "any") or "any",
                    images=getattr(self.settings, "booru_images", True),
                    gifs=getattr(self.settings, "booru_gifs", True),
                    videos=getattr(self.settings, "booru_videos", True),
                    custom_url=custom_url,
                    api_type=api_type,
                    sort=getattr(self.settings, "booru_sort", "") or "",
                )
                url = post.get("file_url") if post else None
                if post and url:
                    self._booru_post_url = booru.post_url(site, post, custom_url, api_type)
                    logging.info(f"booru post: id={post.get('id')} site={site} -> {self._booru_post_url}")
                    data = booru.fetch_bytes(url)
                    fd, tmp = tempfile.mkstemp(suffix=f".{booru.url_ext(url)}")
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                    self._booru_tmp = tmp
                    return tmp
                logging.error(f'No results for tags "{self.settings.booru_tags}" on {site}')
            except Exception as e:
                logging.error(f"Booru fetch failed: {e}")
        return self.media

    def _prepare(self, denial_filter) -> None:
        try:
            from features import booru

            source = self._acquire_source()
            # Video (mp4/webm/...) plays through GStreamer; probe dimensions with
            # videoprops since PIL can't open it.
            if booru.url_ext(str(source)) in booru.VIDEO_EXTS:
                from videoprops import get_video_properties

                props = get_video_properties(str(source))
                GLib.idle_add(self._finish_animated, str(source), props["width"], props["height"])
                return
            image = Image.open(source)
            src_w, src_h = image.width, image.height
            if getattr(image, "n_frames", 0) > 1:
                # Animated (GIF) — build the GStreamer widget on the main thread,
                # playing the actual source file (booru temp or pack media).
                GLib.idle_add(self._finish_animated, str(source), src_w, src_h)
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
            if self._use_censor:
                from features import censor

                regions = None
                eye_faces = []
                if self.settings.denial_detect:
                    detected = censor.detect_regions(final)
                    # Optionally union an anime-tuned detector for stylised content.
                    if self.settings.denial_detect_anime:
                        anime = censor.detect_anime_regions(final)
                        if anime is not None:
                            detected = censor.union_detections(detected, anime)
                    # None -> detector unavailable -> censor whole image. Otherwise
                    # keep regions whose part rolls in, honouring the covered toggle.
                    if detected is not None:
                        regions = []
                        for box, part, covered in detected:
                            if covered and not getattr(self.settings, f"censor_part_{part}_covered", True):
                                continue
                            if roll(getattr(self.settings, f"censor_part_{part}", 100)):
                                if part == "face" and self.settings.censor_face_eyes_only:
                                    eye_faces.append(box)  # rotated bar, drawn post-censor
                                else:
                                    regions.append(box)
                caption = self.denial_text if self.settings.denial_caption_in_image else None
                final = censor.apply_censor(
                    final, self.settings.denial_style, self.settings.denial_intensity,
                    regions, caption, invert=self.settings.denial_reverse,
                )
                for fb in eye_faces:
                    censor.draw_eye_bar(final, fb, self.settings.censor_eye_height / 100)
                self._caption_burned = bool(caption)
            pixbuf = pil_to_pixbuf(final)
        except Exception as e:
            logging.warning(f"image popup prepare failed: {e}")
            GLib.idle_add(self.close)  # release the slot + destroy the empty window
            return
        GLib.idle_add(self._finish_still, pixbuf)

    def _finish_animated(self, source, src_w: int, src_h: int) -> bool:
        self.compute_geometry(src_w, src_h)
        video, self._media_file = video_widget(
            source,
            self.width,
            self.height,
            loop=True,
            volume=self.settings.video_volume / 100,
            blur=self.denial,
            hardware_acceleration=self.settings.video_hardware_acceleration,
        )
        self.set_media_widget(video)
        self._add_source_button()
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

        self._add_source_button()
        self.init_finish()
        return False

    def _add_source_button(self) -> None:
        """If this popup shows a booru post, overlay a small button (top-right)
        that opens the post page in the browser."""
        if not self._booru_post_url:
            return
        logging.info(f"booru post: adding source button -> {self._booru_post_url}")
        button = Gtk.Button(icon_name="applications-internet-symbolic")
        button.add_css_class("popup-close")
        button.set_tooltip_text("Open booru post")
        button.set_halign(Gtk.Align.END)
        button.set_valign(Gtk.Align.START)
        button.set_margin_end(10)
        button.set_margin_top(10)
        button.connect("clicked", self._open_source)
        self._overlay.add_overlay(button)

    def _open_source(self, _button: Gtk.Button) -> None:
        url = self._booru_post_url
        if not url:
            return
        logging.info(f"booru post: opening {url}")
        # Hand off to the desktop portal (see os_utils.open_url). Do NOT use
        # Gtk.UriLauncher (parents to our layer-shell surface -> Wayland Error
        # 71) or spawn the browser as our direct child (inherits GTK state and
        # can crash it).
        import os_utils
        os_utils.open_url(url)

    def should_init(self, settings: Settings, state: State) -> bool:
        if self.media and state.image_number < settings.max_image:
            state.image_number += 1
            return True
        return False

    def close(self) -> None:
        stop_media(self._media_file)
        if self._booru_tmp:
            try:
                import os

                os.unlink(self._booru_tmp)
            except OSError:
                pass
            self._booru_tmp = None
        super().close()
        self.state.image_number -= 1
