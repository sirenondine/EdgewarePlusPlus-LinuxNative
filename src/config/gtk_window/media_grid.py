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

"""Phase 2C: media -> mood assignment grid.

Uses Gtk.GridView (virtualised — only on-screen tiles exist) so packs with
hundreds/thousands of files don't hitch. Thumbnails decode lazily on a single
worker thread when a tile is bound, cached by path. Each tab (Images / Videos /
Audio) supports adding files and deleting them; each tile has a mood dropdown,
a colour strip, and a lightbox / play action.
"""

import os
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

TILE_W = 120
TILE_H = 120

_UNASSIGNED_LABEL = "All moods"

# Extension sets used by _list_files — avoids reading every file's magic bytes
# (filetype.is_image etc.) which blocks the main thread for large packs.
_TYPE_EXTS: dict[str, set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".avif", ".tiff", ".tif"},
    "video": {".mp4", ".webm", ".m4v", ".mov", ".avi", ".mkv", ".flv"},
    "audio": {".mp3", ".ogg", ".wav", ".flac", ".aac", ".m4a", ".opus"},
}
_UNASSIGNED_COLOR = "#888888"
_MOOD_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e91e63", "#ff5722",
]

# Module-level audio playback state: only one file plays at a time.
_audio_player = None
_audio_btn: Gtk.Button | None = None

# Thumbnail cache (path str -> Gdk.Texture) + a single decode worker queue.
_thumb_cache: dict[str, Gdk.Texture] = {}
_thumb_queue: deque = deque()
_thumb_lock = threading.Lock()
_thumb_worker_running = False


def _mood_color(mood: str | None, mood_names: list[str]) -> str:
    if mood is None or mood not in mood_names:
        return _UNASSIGNED_COLOR
    return _MOOD_COLORS[mood_names.index(mood) % len(_MOOD_COLORS)]


def _css_color_id(color: str) -> str:
    return color.lstrip("#")


def _ensure_css() -> None:
    if getattr(_ensure_css, "_done", False):
        return
    _ensure_css._done = True  # type: ignore[attr-defined]
    colors = [_UNASSIGNED_COLOR] + _MOOD_COLORS
    css_parts = [
        b"""
        .media-mood-picker { background-color: rgba(0,0,0,0.60); color: white; border-radius: 0; }
        .media-mood-picker button { background-color: transparent; color: white; }
        .mood-filter-btn { border-radius: 16px; padding: 2px 8px; }
        .media-del-btn { background-color: rgba(0,0,0,0.55); border-radius: 50%; min-width: 22px; min-height: 22px; padding: 0; }
        """
    ]
    for color in colors:
        cid = _css_color_id(color)
        css_parts.append(
            f".mood-strip-{cid} {{ background-color: {color}; }}\n"
            f".mood-dot-{cid}  {{ background-color: {color}; border-radius: 50%; min-width:10px; min-height:10px; }}\n".encode()
        )
    provider = Gtk.CssProvider()
    provider.load_from_data(b"".join(css_parts))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_media_page(pack_dir: Path, editor, on_change: Callable, pop_fn: Callable) -> Adw.NavigationPage:
    _ensure_css()
    mood_names = editor.mood_names()

    stack = Adw.ViewStack()
    stack.set_vexpand(True)

    for name, icon, media_type, sub in (
        ("Images", "image-x-generic-symbolic", "image", "img"),
        ("Videos", "video-x-generic-symbolic", "video", "vid"),
        ("Audio",  "audio-x-generic-symbolic", "audio", "aud"),
    ):
        tab = _MediaTab(pack_dir / sub, media_type, editor, on_change, mood_names)
        vsp = stack.add_titled(tab, name.lower(), name)
        vsp.set_icon_name(icon)

    switcher = Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE)

    back_btn = Gtk.Button()
    back_btn.set_child(Adw.ButtonContent(icon_name="go-previous-symbolic", label="Edit Pack"))
    back_btn.set_halign(Gtk.Align.START)
    back_btn.set_margin_start(6)
    back_btn.connect("clicked", lambda _: pop_fn())

    top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    top_bar.append(back_btn)
    top_bar.append(switcher)

    tv = Adw.ToolbarView()
    tv.add_top_bar(top_bar)
    tv.set_content(stack)
    return Adw.NavigationPage.new(tv, "Media Assignment")


# ---------------------------------------------------------------------------
# One media-type tab (GridView + filter bar + add button)
# ---------------------------------------------------------------------------

class _MediaTab(Gtk.Box):
    def __init__(self, media_dir: Path, media_type: str, editor, on_change, mood_names):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.media_dir = media_dir
        self.media_type = media_type
        self.editor = editor
        self.on_change = on_change
        self.mood_names = mood_names
        self.mood_options = [_UNASSIGNED_LABEL] + mood_names
        self._active_filter = None  # None=all, ""=unassigned, str=mood

        self.model = Gtk.StringList.new(self._list_files())

        self.filter = Gtk.CustomFilter.new(self._match)
        filter_model = Gtk.FilterListModel.new(self.model, self.filter)

        # --- Top action bar: filter pills + Add button ---
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_start(12); bar.set_margin_end(12)
        bar.set_margin_top(8); bar.set_margin_bottom(4)
        bar.append(self._build_filter_bar())
        add_btn = Gtk.Button()
        add_btn.set_child(Adw.ButtonContent(label="Add…", icon_name="list-add-symbolic"))
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.connect("clicked", lambda _: self._on_add())
        bar.append(add_btn)
        self.append(bar)

        # --- GridView ---
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        factory.connect("unbind", self._on_unbind)

        grid = Gtk.GridView(model=Gtk.NoSelection.new(filter_model), factory=factory)
        grid.set_max_columns(99)
        grid.set_min_columns(1)
        grid.add_css_class("media-grid")

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_vexpand(True)
        self._scroller.set_child(grid)
        self.append(self._scroller)

        _ICONS = {"image": "image-x-generic-symbolic",
                  "video": "video-x-generic-symbolic",
                  "audio": "audio-x-generic-symbolic"}
        self._empty = Adw.StatusPage(
            icon_name=_ICONS.get(media_type, "folder-open-symbolic"),
            title=f"No {media_type}s yet",
            description="Use Add… above to import files into this pack.",
        )
        self._empty.set_vexpand(True)
        self.append(self._empty)
        self._update_empty()

    # --- file listing ---
    def _list_files(self) -> list[str]:
        # Extension check only — no magic-byte reads. filetype.is_image() opens
        # every file which blocks the main thread for ~1.3s on a 5000-file pack.
        exts = _TYPE_EXTS.get(self.media_type, set())
        if not self.media_dir.is_dir():
            return []
        try:
            with os.scandir(self.media_dir) as it:
                return sorted(
                    e.name for e in it
                    if e.is_file() and Path(e.name).suffix.lower() in exts
                )
        except Exception:
            return []

    def _update_empty(self) -> None:
        empty = self.model.get_n_items() == 0
        self._empty.set_visible(empty)
        self._scroller.set_visible(not empty)

    # --- filter ---
    def _match(self, item) -> bool:
        filt = self._active_filter
        if filt is None:
            return True
        assigned = self.editor.get_media_assignment(item.get_string())
        return assigned is None if filt == "" else assigned == filt

    def _build_filter_bar(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_hexpand(True)
        scroll.set_min_content_height(36)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_valign(Gtk.Align.CENTER)
        scroll.set_child(bar)
        toggles: list[Gtk.ToggleButton] = []
        _guard = [False]  # re-entrancy guard: prevents mutual set_active() recursion
        opts: list[tuple[str, str | None]] = (
            [("All", None), ("Unassigned", "")] + [(m, m) for m in self.mood_names])
        for label, val in opts:
            btn = Gtk.ToggleButton()
            btn.add_css_class("mood-filter-btn")
            if val is None:
                btn.set_child(Gtk.Label(label="All"))
                btn.set_active(True)
            else:
                color = _UNASSIGNED_COLOR if val == "" else _mood_color(val, self.mood_names)
                dot = Gtk.Box(); dot.set_valign(Gtk.Align.CENTER)
                dot.add_css_class(f"mood-dot-{_css_color_id(color)}")
                inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                inner.set_valign(Gtk.Align.CENTER)
                inner.append(dot); inner.append(Gtk.Label(label=label))
                btn.set_child(inner)

            def on_toggle(b, v=val):
                if _guard[0]:
                    return
                if not b.get_active():
                    # Prevent deactivating the last active button — force it back.
                    _guard[0] = True
                    b.set_active(True)
                    _guard[0] = False
                    return
                _guard[0] = True
                for o in toggles:
                    if o is not b:
                        o.set_active(False)
                _guard[0] = False
                self._active_filter = v
                self.filter.changed(Gtk.FilterChange.DIFFERENT)
            btn.connect("toggled", on_toggle)
            toggles.append(btn)
            bar.append(btn)
        return scroll

    # --- factory: setup / bind / unbind ---
    def _on_setup(self, _factory, item) -> None:
        tile = _Tile(self.media_type, self.mood_options)
        tile.dropdown.connect("notify::selected", lambda d, _p, t=tile: self._on_dropdown(t))
        tile.del_btn.connect("clicked", lambda _b, t=tile: self._on_delete(t.filename))
        item.set_child(tile)

    def _on_bind(self, _factory, item) -> None:
        tile = item.get_child()
        filename = item.get_item().get_string()
        tile._media_dir = self.media_dir
        tile.bind(filename, self.editor.get_media_assignment(filename), self.mood_names)
        if self.media_type in ("image", "video"):
            _queue_thumbnail(self.media_dir / filename, tile, self.media_type)

    def _on_unbind(self, _factory, item) -> None:
        item.get_child().unbind()

    # --- per-tile actions ---
    def _on_dropdown(self, tile: "_Tile") -> None:
        if tile.binding or not tile.filename:
            return
        idx = tile.dropdown.get_selected()
        mood = None if idx == 0 else self.mood_options[idx]
        self.editor.set_media_assignment(tile.filename, mood)
        tile.apply_strip(mood, self.mood_names)
        self.on_change()
        if self._active_filter is not None:
            self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_delete(self, filename: str) -> None:
        if not filename:
            return
        from gtk_dialog import ask_yes_no
        if not ask_yes_no(
            f"Delete {filename}?",
            "The file is removed from the pack and unassigned from its mood.",
            heading="Delete media file?",
        ):
            return
        err = self.editor.delete_media(self.media_type, filename)
        if err:
            from config.gtk_window.toast import toast
            toast(f"Could not delete: {err}")
            return
        self.editor.save_index()
        self.on_change()
        # Drop from the model.
        for i in range(self.model.get_n_items()):
            if self.model.get_string(i) == filename:
                self.model.remove(i)
                break
        self._update_empty()

    def _on_add(self) -> None:
        dlg = Gtk.FileDialog()
        dlg.set_title(f"Add {self.media_type}s")
        filt = Gtk.FileFilter()
        mimes = {
            "image": ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"),
            "video": ("video/mp4", "video/webm", "video/quicktime", "video/x-matroska"),
            "audio": ("audio/mpeg", "audio/wav", "audio/ogg", "audio/flac", "audio/mp4"),
        }[self.media_type]
        filt.set_name(self.media_type.capitalize())
        for m in mimes:
            filt.add_mime_type(m)
        dlg.set_default_filter(filt)
        dlg.open_multiple(self.get_root(), None, self._on_add_selected)

    def _on_add_selected(self, dlg, result) -> None:
        try:
            files = dlg.open_multiple_finish(result)
        except Exception:
            return
        if not files:
            return
        paths = [Path(files.get_item(i).get_path()) for i in range(files.get_n_items())]
        copied, errors = self.editor.import_media(self.media_type, paths)
        for name in copied:
            self.model.append(name)
        from config.gtk_window.toast import toast
        if copied:
            toast(f"Added {len(copied)} file{'s' if len(copied) != 1 else ''}.")
        if errors:
            toast(f"{len(errors)} file(s) failed to import.")
        self._update_empty()


# ---------------------------------------------------------------------------
# A recyclable grid tile
# ---------------------------------------------------------------------------

class _Tile(Gtk.Box):
    def __init__(self, media_type: str, mood_options: list[str]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.media_type = media_type
        self.filename = ""
        self.binding = False
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)

        self.strip = Gtk.Box()
        self.strip.set_size_request(-1, 5)
        self.append(self.strip)

        overlay = Gtk.Overlay()
        overlay.set_size_request(TILE_W, TILE_H)

        if media_type == "image":
            self.picture = Gtk.Picture()
            self.picture.set_size_request(TILE_W, TILE_H)
            self.picture.set_content_fit(Gtk.ContentFit.COVER)
            self.picture.set_can_shrink(True)
            overlay.set_child(self.picture)
            click = Gtk.GestureClick.new()
            click.connect("pressed", lambda *_: _open_lightbox(
                self._full_path(), self.get_root()))
            self.picture.add_controller(click)
        elif media_type == "video":
            # Thumbnail (first frame) behind a centred play button.
            self.picture = Gtk.Picture()
            self.picture.set_size_request(TILE_W, TILE_H)
            self.picture.set_content_fit(Gtk.ContentFit.COVER)
            self.picture.set_can_shrink(True)
            overlay.set_child(self.picture)
            play = Gtk.Button(icon_name="media-playback-start-symbolic")
            play.add_css_class("osd")
            play.set_halign(Gtk.Align.CENTER)
            play.set_valign(Gtk.Align.CENTER)
            play.connect("clicked", lambda _b: _open_animated_lightbox(
                self._full_path(), self.get_root()))
            overlay.add_overlay(play)
        else:  # audio
            self.picture = None
            play = Gtk.Button(icon_name="media-playback-start-symbolic")
            play.set_size_request(TILE_W, TILE_H)
            play.add_css_class("flat")
            self.play_btn = play
            play.connect("clicked", lambda _b: _toggle_audio(self._full_path(), play))
            overlay.set_child(play)

        self.dropdown = Gtk.DropDown(model=Gtk.StringList.new(mood_options))
        self.dropdown.set_valign(Gtk.Align.END)
        self.dropdown.set_halign(Gtk.Align.FILL)
        self.dropdown.add_css_class("media-mood-picker")
        overlay.add_overlay(self.dropdown)

        self.del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        self.del_btn.add_css_class("media-del-btn")
        self.del_btn.set_halign(Gtk.Align.END)
        self.del_btn.set_valign(Gtk.Align.START)
        self.del_btn.set_margin_top(3); self.del_btn.set_margin_end(3)
        self.del_btn.set_tooltip_text("Delete file")
        overlay.add_overlay(self.del_btn)

        self.append(overlay)

        self.name_lbl = Gtk.Label()
        self.name_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.name_lbl.set_max_width_chars(14)
        self.name_lbl.add_css_class("caption")
        self.append(self.name_lbl)

        self._media_dir: Path | None = None

    def _full_path(self) -> Path:
        return (self._media_dir / self.filename) if self._media_dir else Path(self.filename)

    def bind(self, filename: str, mood: str | None, mood_names: list[str]) -> None:
        self.binding = True
        self.filename = filename
        self.name_lbl.set_text(filename)
        opts = [_UNASSIGNED_LABEL] + mood_names
        self.dropdown.set_selected(opts.index(mood) if mood in opts else 0)
        self.apply_strip(mood, mood_names)
        if self.picture is not None:
            self.picture.set_paintable(None)  # cleared until thumbnail arrives
        self.binding = False

    def unbind(self) -> None:
        self.filename = ""
        if self.picture is not None:
            self.picture.set_paintable(None)

    def apply_strip(self, mood: str | None, mood_names: list[str]) -> None:
        for cls in list(self.strip.get_css_classes()):
            if cls.startswith("mood-strip-"):
                self.strip.remove_css_class(cls)
        self.strip.add_css_class(f"mood-strip-{_css_color_id(_mood_color(mood, mood_names))}")


# ---------------------------------------------------------------------------
# Lazy thumbnail loading (single worker thread + cache)
# ---------------------------------------------------------------------------

def _queue_thumbnail(path: Path, tile: _Tile, media_type: str = "image") -> None:
    if tile.picture is None:
        return
    tile._media_dir = path.parent
    key = str(path)
    cached = _thumb_cache.get(key)
    if cached is not None:
        tile.picture.set_paintable(cached)
        return
    with _thumb_lock:
        _thumb_queue.append((key, path, tile, tile.filename, media_type))
        _start_thumb_worker()


def _start_thumb_worker() -> None:
    global _thumb_worker_running
    if _thumb_worker_running:
        return
    _thumb_worker_running = True
    threading.Thread(target=_thumb_worker, daemon=True).start()


def _thumb_worker() -> None:
    global _thumb_worker_running
    while True:
        with _thumb_lock:
            if not _thumb_queue:
                _thumb_worker_running = False
                return
            key, path, tile, expected, media_type = _thumb_queue.popleft()  # FIFO: top-to-bottom
        texture = _thumb_cache.get(key)
        if texture is None:
            try:
                if media_type == "video":
                    texture = _video_thumbnail(path)
                else:
                    texture = _image_thumbnail(path)
            except Exception:
                texture = None
            if texture is None:
                continue
            _thumb_cache[key] = texture
        GLib.idle_add(_apply_thumb, tile, expected, texture)


def _image_thumbnail(path: Path) -> "Gdk.Texture | None":
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    img.thumbnail((TILE_W, TILE_H), Image.LANCZOS)
    w, h = img.size
    pb = GdkPixbuf.Pixbuf.new_from_data(
        img.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4)
    return Gdk.Texture.new_for_pixbuf(pb)


def _load_image_texture(path: Path) -> "Gdk.Texture | None":
    """Load a full-size image via PIL. Handles WebP, AVIF, and other formats
    that GdkPixbuf may not support without optional loader plugins."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        pb = GdkPixbuf.Pixbuf.new_from_data(
            img.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4)
        return Gdk.Texture.new_for_pixbuf(pb)
    except Exception:
        return None


def _video_thumbnail(path: Path) -> "Gdk.Texture | None":
    """Grab a frame ~1s into the video via GStreamer and return it as a texture.
    Blocking — call from the worker thread only."""
    require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)

    pipeline = Gst.parse_launch(
        f'uridecodebin uri="{path.as_uri()}" ! videoconvert ! videoscale ! '
        f'appsink name=sink caps="video/x-raw,format=RGB,pixel-aspect-ratio=1/1"')
    sink = pipeline.get_by_name("sink")
    try:
        pipeline.set_state(Gst.State.PAUSED)
        # Wait for preroll (negotiated caps available).
        if pipeline.get_state(5 * Gst.SECOND)[0] != Gst.StateChangeReturn.SUCCESS:
            return None
        # Seek ~1s in for a non-black frame (clamped for very short clips).
        dur = pipeline.query_duration(Gst.Format.TIME)[1]
        seek_to = min(1 * Gst.SECOND, dur // 2) if dur > 0 else 0
        if seek_to:
            pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, seek_to)
            pipeline.get_state(5 * Gst.SECOND)
        sample = sink.emit("pull-preroll")
        if sample is None:
            return None
        caps = sample.get_caps().get_structure(0)
        w, h = caps.get_value("width"), caps.get_value("height")
        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            rowstride = (w * 3 + 3) & ~3  # GStreamer pads RGB rows to 4 bytes
            pb = GdkPixbuf.Pixbuf.new_from_data(
                bytes(mapinfo.data), GdkPixbuf.Colorspace.RGB, False, 8, w, h, rowstride)
            # Scale down to tile size.
            scale = min(TILE_W / w, TILE_H / h, 1.0)
            pb = pb.scale_simple(max(1, round(w * scale)), max(1, round(h * scale)),
                                 GdkPixbuf.InterpType.BILINEAR)
            return Gdk.Texture.new_for_pixbuf(pb)
        finally:
            buf.unmap(mapinfo)
    finally:
        pipeline.set_state(Gst.State.NULL)


def _apply_thumb(tile: _Tile, expected: str, texture: Gdk.Texture) -> bool:
    if tile.picture is not None and tile.filename == expected:
        tile.picture.set_paintable(texture)
    return False


# ---------------------------------------------------------------------------
# Lightboxes + audio
# ---------------------------------------------------------------------------

_ANIMATED_EXTS = {".gif", ".webm", ".mp4", ".m4v", ".mov", ".avi", ".mkv"}


def _open_lightbox(path: Path, root) -> None:
    if path.suffix.lower() in _ANIMATED_EXTS:
        _open_animated_lightbox(path, root)
        return
    dialog = Adw.Dialog()
    dialog.set_title(path.name)
    dialog.set_content_width(900)
    dialog.set_content_height(700)
    texture = _load_image_texture(path)
    picture = (Gtk.Picture.new_for_paintable(texture) if texture
               else Gtk.Picture.new_for_filename(str(path)))
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_can_shrink(True)
    picture.set_vexpand(True); picture.set_hexpand(True)
    click = Gtk.GestureClick.new()
    click.connect("pressed", lambda *_: dialog.close())
    picture.add_controller(click)
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(picture)
    dialog.set_child(tv)
    dialog.present(root)


def _open_animated_lightbox(path: Path, root) -> None:
    dialog = Adw.Dialog()
    dialog.set_title(path.name)
    dialog.set_content_width(900)
    dialog.set_content_height(640)
    media = Gtk.MediaFile.new_for_filename(str(path))
    video = Gtk.Video(media_stream=media)
    video.set_loop(False)
    video.set_vexpand(True); video.set_hexpand(True)
    video.connect("realize", lambda _w: media.play())
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(video)
    dialog.set_child(tv)
    dialog.present(root)


def _toggle_audio(path: Path, play_btn: Gtk.Button) -> None:
    global _audio_player, _audio_btn
    try:
        require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
    except Exception:
        return
    if _audio_player is not None and getattr(_audio_player, "_path", None) == path:
        _ret, state, _pending = _audio_player.get_state(Gst.CLOCK_TIME_NONE)
        if state == Gst.State.PLAYING:
            _audio_player.set_state(Gst.State.PAUSED)
            play_btn.set_icon_name("media-playback-start-symbolic")
        else:
            _audio_player.set_state(Gst.State.PLAYING)
            play_btn.set_icon_name("media-playback-pause-symbolic")
        return
    if _audio_player is not None:
        _audio_player.set_state(Gst.State.NULL)
    if _audio_btn is not None and _audio_btn is not play_btn:
        _audio_btn.set_icon_name("media-playback-start-symbolic")
    player = Gst.ElementFactory.make("playbin", None)
    player._path = path  # type: ignore[attr-defined]
    player.set_property("uri", path.as_uri())
    bus = player.get_bus(); bus.add_signal_watch()
    def _on_message(_bus, msg, btn=play_btn) -> bool:
        from gi.repository import Gst as G
        if msg.type == G.MessageType.EOS:
            player.set_state(G.State.NULL)
            GLib.idle_add(btn.set_icon_name, "media-playback-start-symbolic")
        return True
    bus.connect("message", _on_message)
    player.set_state(Gst.State.PLAYING)
    play_btn.set_icon_name("media-playback-pause-symbolic")
    _audio_player = player
    _audio_btn = play_btn
