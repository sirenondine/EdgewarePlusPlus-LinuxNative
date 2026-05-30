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

"""Native GTK4 media helpers — replaces the Tkinter/mpv rendering path.

Video uses an explicit GStreamer `playbin` pipeline rendering into a
`gtk4paintablesink`, deliberately avoiding `playbin3`/`decodebin3` which
asserts-and-aborts the whole process on some files."""

import logging
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import GdkPixbuf, GLib, Gst, Gtk
from PIL import Image

_GST_READY = False


def _ensure_gst() -> None:
    global _GST_READY
    if not _GST_READY:
        Gst.init(None)
        _GST_READY = True


def pil_to_pixbuf(image: Image.Image) -> GdkPixbuf.Pixbuf:
    """Convert a PIL image to a GdkPixbuf (RGBA)."""
    image = image.convert("RGBA")
    data = GLib.Bytes.new(image.tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(
        data,
        GdkPixbuf.Colorspace.RGB,
        True,  # has_alpha
        8,
        image.width,
        image.height,
        image.width * 4,  # rowstride
    )


def picture_from_pil(image: Image.Image, width: int, height: int) -> Gtk.Picture:
    """Build a fixed-size Gtk.Picture from a PIL image."""
    picture = Gtk.Picture.new_for_pixbuf(pil_to_pixbuf(image))
    picture.set_size_request(width, height)
    picture.set_content_fit(Gtk.ContentFit.FILL)
    return picture


class VideoController:
    """Plays a video file via GStreamer playbin into a Gtk.Picture.

    Keeps playing regardless of window focus/occlusion and loops by seeking
    to the start on EOS."""

    def __init__(self, media: Path, width: int, height: int, loop: bool = True, volume: float | None = None, muted: bool = False, blur: bool = False, hardware_acceleration: bool = True) -> None:
        _ensure_gst()
        self._loop = loop
        self._stopped = False

        self._playbin = Gst.ElementFactory.make("playbin", None)
        sink = Gst.ElementFactory.make("gtk4paintablesink", None)

        self.widget = Gtk.Picture()
        self.widget.set_size_request(width, height)
        self.widget.set_content_fit(Gtk.ContentFit.FILL)

        if self._playbin is None or sink is None:
            logging.error("GStreamer playbin/gtk4paintablesink unavailable; video will not render")
            return

        self._playbin.set_property("video-sink", sink)
        self.widget.set_paintable(sink.get_property("paintable"))

        # Honor the "hardware acceleration" toggle where the GStreamer build
        # supports forcing software decoders; otherwise playbin auto-selects.
        if not hardware_acceleration:
            try:
                self._playbin.set_property("force-sw-decoders", True)
            except (TypeError, GLib.Error):
                logging.info("force-sw-decoders unsupported by this playbin; using auto decoder selection")

        # Denial: censor the video with a heavy gaussian blur (mirrors the PIL
        # blur applied to still images).
        if blur:
            import random
            blur_el = Gst.ElementFactory.make("gaussianblur", None)
            if blur_el is not None:
                blur_el.set_property("sigma", random.uniform(6.0, 14.0))
                self._playbin.set_property("video-filter", blur_el)

        self._playbin.set_property("uri", Gst.filename_to_uri(str(media)))
        if muted:
            self._playbin.set_property("mute", True)
        elif volume is not None:
            self._playbin.set_property("volume", max(0.0, min(1.0, volume)))

        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        bus.connect("message::error", self._on_error)

        self._playbin.set_state(Gst.State.PLAYING)

    def _on_eos(self, _bus, _msg) -> None:
        if self._loop and not self._stopped:
            self._playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
        else:
            self.stop()

    def _on_error(self, _bus, msg) -> None:
        err, _debug = msg.parse_error()
        logging.warning(f"GStreamer video error: {err}")
        self.stop()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._playbin is not None:
            bus = self._playbin.get_bus()
            if bus:
                bus.remove_signal_watch()
            self._playbin.set_state(Gst.State.NULL)


def video_widget(media: Path, width: int, height: int, loop: bool = True, volume: float | None = None, muted: bool = False, blur: bool = False, hardware_acceleration: bool = True) -> tuple[Gtk.Widget, VideoController]:
    """Build a video widget. Returns (picture_widget, controller)."""
    controller = VideoController(media, width, height, loop=loop, volume=volume, muted=muted, blur=blur, hardware_acceleration=hardware_acceleration)
    return controller.widget, controller


def stop_media(controller: VideoController | None) -> None:
    """Stop playback and tear down the pipeline (for popup close)."""
    if controller is not None:
        controller.stop()
