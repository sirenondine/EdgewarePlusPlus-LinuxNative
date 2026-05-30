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
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

from config.settings import Settings
from features.gtk_media import _ensure_gst
from pack import Pack
from state import State

TICKRATE = 16  # ~60 ticks/s


class AudioController:
    """Plays an audio file via GStreamer playbin (avoids playbin3/decodebin3,
    which aborts the process on some files)."""

    def __init__(self, path: Path, volume: float, fade_in_ms: int, fade_out_ms: int, on_done: Callable[[], None]) -> None:
        _ensure_gst()
        self._target = max(0.0, min(1.0, volume))
        self._fade_out_ms = fade_out_ms
        self._on_done = on_done
        self._stopped = False

        self._playbin = Gst.ElementFactory.make("playbin", None)
        if self._playbin is None:
            logging.error("GStreamer playbin unavailable; audio will not play")
            self._on_done()
            return

        # Audio only — discard any video stream.
        self._playbin.set_property("video-sink", Gst.ElementFactory.make("fakesink", None))
        self._playbin.set_property("uri", Gst.filename_to_uri(str(path)))
        self._playbin.set_property("volume", 0.0)

        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", lambda *_: self.stop())
        bus.connect("message::error", self._on_error)

        self._playbin.set_state(Gst.State.PLAYING)
        self._ramp(0.0, self._target, fade_in_ms)
        self._await_duration()

    def _on_error(self, _bus, msg) -> None:
        err, _debug = msg.parse_error()
        logging.warning(f"GStreamer audio error: {err}")
        self.stop()

    def _ramp(self, start: float, end: float, duration_ms: int) -> None:
        steps = max(1, duration_ms // TICKRATE)
        delta = (end - start) / steps
        self._playbin.set_property("volume", start)

        def step() -> bool:
            if self._stopped:
                return GLib.SOURCE_REMOVE
            vol = self._playbin.get_property("volume") + delta
            done = vol >= end if delta >= 0 else vol <= end
            self._playbin.set_property("volume", max(0.0, min(end if delta >= 0 else start, vol)))
            return GLib.SOURCE_REMOVE if done else GLib.SOURCE_CONTINUE

        GLib.timeout_add(TICKRATE, step)

    def _await_duration(self, attempts: int = 0) -> bool:
        if self._stopped:
            return GLib.SOURCE_REMOVE
        ok, duration = self._playbin.query_duration(Gst.Format.TIME)
        if ok and duration > 0:
            duration_ms = duration // Gst.MSECOND
            fade_out = min(self._fade_out_ms, duration_ms)
            GLib.timeout_add(max(0, duration_ms - fade_out), lambda: (self._ramp(self._target, 0.0, fade_out), GLib.SOURCE_REMOVE)[1])
            return GLib.SOURCE_REMOVE
        if attempts > 20:  # ~2s of polling
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(100, lambda: self._await_duration(attempts + 1))
        return GLib.SOURCE_REMOVE

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._playbin is not None:
            bus = self._playbin.get_bus()
            if bus:
                bus.remove_signal_watch()
            self._playbin.set_state(Gst.State.NULL)
        self._on_done()


def play_audio(settings: Settings, pack: Pack, state: State, audio: Path | None = None, on_stop: Callable[[], None] | None = None) -> None:
    audio = audio or pack.random_audio()
    if not audio or len(state.audio_players) >= settings.max_audio:
        return

    holder = {}

    def on_done() -> None:
        if holder.get("ctrl") in state.audio_players:
            state.audio_players.remove(holder["ctrl"])
        if on_stop:
            GLib.idle_add(on_stop)

    ctrl = AudioController(
        audio,
        volume=settings.audio_volume,  # already 0..1 (to_float)
        fade_in_ms=settings.fade_in_duration,
        fade_out_ms=settings.fade_out_duration,
        on_done=on_done,
    )
    holder["ctrl"] = ctrl
    state.audio_players.append(ctrl)
