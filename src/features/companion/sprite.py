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
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

# Animated companion sprites, compatible with the codex-pet-share spritesheet
# layout (https://github.com/portons/codex-pet-share): a sheet of 8 frame
# columns x 9 state rows, so any pet published in that format drops straight in.
# The canonical sheet is 1536x1872 (192x208 cells), but the cell size is derived
# from the actual image so off-spec sheets still load.
#
# That format is CI-themed (idle/running/review/...); we only need a few of the
# rows, remapped to companion behaviour (see *_STATE below). Frames are sliced
# with PIL (releases the GIL) and cached as Gdk textures; a GLib timer advances
# the current row at its fps.

import logging
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk
from PIL import Image

from features.gtk_media import pil_to_pixbuf

ATLAS_COLS = 8
ATLAS_ROWS = 9


@dataclass(frozen=True)
class StateDef:
    row: int
    frames: int
    fps: int
    loop: bool


# Mirror of codex-pet-share src/playground/core/config.ts STATES, so community
# sheets animate with their intended timing.
STATES: dict[str, StateDef] = {
    "idle": StateDef(0, 6, 6, True),
    "running-right": StateDef(1, 8, 12, True),
    "running-left": StateDef(2, 8, 12, True),
    "waving": StateDef(3, 4, 5, False),
    "jumping": StateDef(4, 5, 14, False),
    "failed": StateDef(5, 8, 6, False),
    "waiting": StateDef(6, 6, 4, True),
    "running": StateDef(7, 6, 12, True),
    "review": StateDef(8, 6, 6, True),
}

# Companion -> codex row remap. No "talking" row exists; "waiting" (attentive,
# gentle loop) reads best while the companion speaks.
IDLE_STATE = "idle"
TALK_STATE = "waiting"
GREET_STATE = "waving"


class SpriteSheet:
    """Decoded spritesheet with lazily-cached per-cell textures."""

    def __init__(self, path) -> None:
        self._image = Image.open(path).convert("RGBA")
        self.cols, self.rows = ATLAS_COLS, ATLAS_ROWS
        self.cell_w = self._image.width // self.cols
        self.cell_h = self._image.height // self.rows
        if (self._image.width, self._image.height) != (1536, 1872):
            logging.info(
                f"Companion spritesheet {path} is {self._image.width}x{self._image.height} "
                f"(canonical is 1536x1872); using derived {self.cell_w}x{self.cell_h} cells."
            )
        self._cache: dict[tuple[int, int], Gdk.Texture] = {}

    @property
    def cell_size(self) -> tuple[int, int]:
        return self.cell_w, self.cell_h

    def texture(self, row: int, col: int) -> Gdk.Texture:
        key = (row, col)
        tex = self._cache.get(key)
        if tex is None:
            x, y = col * self.cell_w, row * self.cell_h
            cell = self._image.crop((x, y, x + self.cell_w, y + self.cell_h))
            tex = Gdk.Texture.new_for_pixbuf(pil_to_pixbuf(cell))
            self._cache[key] = tex
        return tex


class SpriteWidget(Gtk.Picture):
    """A Gtk.Picture that plays SpriteSheet states. set_state() drives it; a
    non-looping state runs once then calls on_finish (default: revert to idle)."""

    def __init__(self, sheet: SpriteSheet, *, scale: float = 1.0) -> None:
        super().__init__()
        self.sheet = sheet
        self.set_content_fit(Gtk.ContentFit.CONTAIN)
        w, h = sheet.cell_size
        self.set_size_request(int(w * scale), int(h * scale))
        self._timer: int | None = None
        self._state: StateDef | None = None
        self._frame = 0
        self._on_finish = None
        self.set_state(IDLE_STATE)

    def set_state(self, name: str, on_finish=None) -> None:
        state = STATES.get(name) or STATES[IDLE_STATE]
        self._stop()
        self._state = state
        self._frame = 0
        self._on_finish = on_finish
        self._show(0)
        interval = max(1, int(1000 / max(1, state.fps)))
        self._timer = GLib.timeout_add(interval, self._tick)

    def _show(self, col: int) -> None:
        self.set_paintable(self.sheet.texture(self._state.row, col))

    def _tick(self) -> bool:
        self._frame += 1
        if self._frame >= self._state.frames:
            if self._state.loop:
                self._frame = 0
            else:
                self._timer = None
                cb, self._on_finish = self._on_finish, None
                (cb or (lambda: self.set_state(IDLE_STATE)))()
                return GLib.SOURCE_REMOVE
        self._show(self._frame)
        return GLib.SOURCE_CONTINUE

    def _stop(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def stop(self) -> None:
        self._stop()


def load_sheet(path) -> SpriteSheet | None:
    try:
        return SpriteSheet(path)
    except Exception as e:
        logging.warning(f"Failed to load companion spritesheet {path}: {e}")
        return None
