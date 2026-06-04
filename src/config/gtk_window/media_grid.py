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

FlowBox of thumbnail tiles per media type (Images / Videos / Audio).
Each tile has:
  - A color strip at the top indicating its assigned mood.
  - A mood DropDown overlaid at the bottom.
  - Click (image) → lightbox; click (video) → video player; click (audio) → play/pause.

A filter bar above each FlowBox lets the user show only files for one mood.
"""

import os
from collections.abc import Callable
from pathlib import Path
from threading import Thread

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

TILE_W = 120
TILE_H = 120

_UNASSIGNED_LABEL = "All moods"   # shown in the per-tile dropdown
_UNASSIGNED_COLOR = "#888888"     # grey strip for unassigned files

# 8-colour palette for mood identification, assigned by index in mood_names.
_MOOD_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e91e63", "#ff5722",
]

# Module-level audio state: only one file plays at a time.
_audio_player = None
_audio_btn: Gtk.Button | None = None


def _mood_color(mood: str | None, mood_names: list[str]) -> str:
    if mood is None or mood not in mood_names:
        return _UNASSIGNED_COLOR
    return _MOOD_COLORS[mood_names.index(mood) % len(_MOOD_COLORS)]


def _apply_strip_color(strip: Gtk.Box, mood: str | None, mood_names: list[str]) -> None:
    for cls in strip.get_css_classes():
        if cls.startswith("mood-strip-"):
            strip.remove_css_class(cls)
    color = _mood_color(mood, mood_names)
    strip.add_css_class(f"mood-strip-{_css_color_id(color)}")


def _css_color_id(color: str) -> str:
    return color.lstrip("#")


def _ensure_css() -> None:
    if getattr(_ensure_css, "_done", False):
        return
    _ensure_css._done = True  # type: ignore[attr-defined]

    colors = [_UNASSIGNED_COLOR] + _MOOD_COLORS
    css_parts = [
        b"""
        .media-mood-picker {
            background-color: rgba(0,0,0,0.60);
            color: white;
            border-radius: 0;
        }
        .media-mood-picker button { background-color: transparent; color: white; }
        .mood-filter-btn { border-radius: 16px; padding: 2px 8px; }
        """
    ]
    for color in colors:
        cid = _css_color_id(color)
        css_parts.append(
            f".mood-strip-{cid} {{ background-color: {color}; }}\n"
            f".mood-dot-{cid}  {{ background-color: {color}; border-radius: 50%; min-width:10px; min-height:10px; }}\n"
            .encode()
        )

    provider = Gtk.CssProvider()
    provider.load_from_data(b"".join(css_parts))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_media_page(
    pack_dir: Path,
    editor,
    on_change: Callable,
    pop_fn: Callable,
) -> Adw.NavigationPage:
    _ensure_css()
    import filetype

    img_files = _list_dir(pack_dir / "img", filetype.is_image)
    vid_files = _list_dir(pack_dir / "vid", filetype.is_video)
    aud_files = _list_dir(pack_dir / "aud", filetype.is_audio)

    mood_names = editor.mood_names()
    mood_options = [_UNASSIGNED_LABEL] + mood_names   # dropdown options

    stack = Adw.ViewStack()
    stack.set_vexpand(True)

    for files, name, icon, media_type in (
        (img_files, "Images", "image-x-generic-symbolic", "image"),
        (vid_files, "Videos", "video-x-generic-symbolic", "video"),
        (aud_files, "Audio",  "audio-x-generic-symbolic", "audio"),
    ):
        tab = _build_tab(files, mood_options, mood_names, editor, on_change, name, media_type)
        vsp = stack.add_titled(tab, name.lower(), name)
        vsp.set_icon_name(icon)

    switcher = Adw.ViewSwitcher()
    switcher.set_stack(stack)
    switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

    back_btn = Gtk.Button()
    back_btn.set_child(Adw.ButtonContent(
        icon_name="go-previous-symbolic", label="Edit Pack"))
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
# Tab building
# ---------------------------------------------------------------------------

def _list_dir(directory: Path, is_valid: Callable) -> list[Path]:
    if not directory.is_dir():
        return []
    try:
        return sorted(
            directory / f for f in os.listdir(directory)
            if (directory / f).is_file() and is_valid(directory / f)
        )
    except Exception:
        return []


def _build_tab(
    files: list[Path],
    mood_options: list[str],
    mood_names: list[str],
    editor,
    on_change: Callable,
    tab_name: str,
    media_type: str,
) -> Gtk.Widget:
    if not files:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_vexpand(True)
        box.set_valign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=f"No {tab_name.lower()} in this pack.")
        lbl.add_css_class("dim-label")
        box.append(lbl)
        return box

    # --- FlowBox ---
    flowbox = Gtk.FlowBox()
    flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
    flowbox.set_homogeneous(True)
    flowbox.set_column_spacing(8)
    flowbox.set_row_spacing(8)
    flowbox.set_margin_start(12)
    flowbox.set_margin_end(12)
    flowbox.set_margin_top(8)
    flowbox.set_margin_bottom(12)
    flowbox.set_max_children_per_line(999)

    # active_filter: None = show all, "" = show unassigned, str = mood name
    active_filter: list[str | None] = [None]

    def do_filter(child: Gtk.FlowBoxChild) -> bool:
        fname = getattr(child, "_filename", None)
        filt = active_filter[0]
        if fname is None or filt is None:
            return True
        assigned = editor.get_media_assignment(fname)
        if filt == "":
            return assigned is None
        return assigned == filt

    flowbox.set_filter_func(do_filter)

    # --- Filter bar ---
    filter_bar = _build_filter_bar(mood_names, active_filter, flowbox)

    # --- Tiles ---
    pending_loads: list[tuple[Gtk.Picture, Path]] = []

    for i, path in enumerate(files):
        tile, picture = _build_tile(
            path, mood_options, mood_names, editor, on_change,
            media_type, flowbox.invalidate_filter,
        )
        flowbox.append(tile)
        child = flowbox.get_child_at_index(i)
        if child:
            child._filename = path.name  # type: ignore[attr-defined]
        if picture is not None:
            pending_loads.append((picture, path))

    if pending_loads:
        Thread(target=_load_thumbnails, args=(pending_loads,), daemon=True).start()

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    scroller.set_child(flowbox)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.append(filter_bar)
    outer.append(scroller)
    return outer


def _build_filter_bar(
    mood_names: list[str],
    active_filter: list,
    flowbox: Gtk.FlowBox,
) -> Gtk.Widget:
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    scroll.set_margin_start(12)
    scroll.set_margin_end(12)
    scroll.set_margin_top(6)
    scroll.set_min_content_height(36)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    bar.set_valign(Gtk.Align.CENTER)
    scroll.set_child(bar)

    toggle_btns: list[Gtk.ToggleButton] = []

    # Options: All, Unassigned, then each mood
    filter_opts: list[tuple[str, str | None]] = (
        [("All", None), ("Unassigned", "")]
        + [(m, m) for m in mood_names]
    )

    for label, filt_val in filter_opts:
        btn = Gtk.ToggleButton()
        btn.add_css_class("mood-filter-btn")

        dot = Gtk.Box()
        dot.set_valign(Gtk.Align.CENTER)
        if filt_val is None:            # All — no dot
            content = Gtk.Label(label="All")
        else:
            color = _UNASSIGNED_COLOR if filt_val == "" else _mood_color(filt_val, mood_names)
            cid = _css_color_id(color)
            dot.add_css_class(f"mood-dot-{cid}")
            lbl = Gtk.Label(label=label)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            row.set_valign(Gtk.Align.CENTER)
            row.append(dot)
            row.append(lbl)
            content = row  # type: ignore[assignment]

        btn.set_child(content)
        if filt_val is None:
            btn.set_active(True)  # "All" starts active

        def on_toggle(b: Gtk.ToggleButton, fv=filt_val) -> None:
            if not b.get_active():
                b.set_active(True)   # prevent deactivating all
                return
            for other in toggle_btns:
                if other is not b:
                    other.set_active(False)
            active_filter[0] = fv
            flowbox.invalidate_filter()

        btn.connect("toggled", on_toggle)
        toggle_btns.append(btn)
        bar.append(btn)

    return scroll


# ---------------------------------------------------------------------------
# Tile building
# ---------------------------------------------------------------------------

def _build_tile(
    path: Path,
    mood_options: list[str],
    mood_names: list[str],
    editor,
    on_change: Callable,
    media_type: str,
    invalidate_fn: Callable,
) -> tuple[Gtk.Widget, "Gtk.Picture | None"]:
    filename = path.name
    picture: Gtk.Picture | None = None

    # Color strip at the top (mood indicator)
    current_mood = editor.get_media_assignment(filename)
    strip = Gtk.Box()
    strip.set_size_request(-1, 5)
    _apply_strip_color(strip, current_mood, mood_names)

    # Thumbnail / icon area
    overlay = Gtk.Overlay()
    overlay.set_size_request(TILE_W, TILE_H)

    if media_type == "image":
        picture = Gtk.Picture()
        picture.set_size_request(TILE_W, TILE_H)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        overlay.set_child(picture)
        # Gesture on picture (not overlay): clicks on the dropdown above go to the
        # dropdown and don't propagate down, so only bare-image clicks open lightbox.
        click = Gtk.GestureClick.new()
        click.connect("pressed", lambda _g, _n, _x, _y, p=path:
                      _open_lightbox(p, picture.get_root()))
        picture.add_controller(click)

    elif media_type == "audio":
        play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        play_btn.set_size_request(TILE_W, TILE_H)
        play_btn.add_css_class("flat")
        play_btn.connect("clicked", lambda _b, p=path: _toggle_audio(p, play_btn))
        overlay.set_child(play_btn)

    else:  # video
        bg = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        bg.set_pixel_size(48)
        bg.set_size_request(TILE_W, TILE_H)
        bg.add_css_class("dim-label")
        play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        play_btn.set_size_request(TILE_W, TILE_H)
        play_btn.add_css_class("flat")
        play_btn.connect("clicked", lambda _b, p=path:
                         _open_video_lightbox(p, play_btn.get_root()))
        vid_ov = Gtk.Overlay()
        vid_ov.set_size_request(TILE_W, TILE_H)
        vid_ov.set_child(bg)
        vid_ov.add_overlay(play_btn)
        overlay.set_child(vid_ov)

    # Mood dropdown overlaid at bottom
    model = Gtk.StringList.new(mood_options)
    dropdown = Gtk.DropDown(model=model)
    dropdown.set_valign(Gtk.Align.END)
    dropdown.set_halign(Gtk.Align.FILL)
    dropdown.add_css_class("media-mood-picker")
    idx = mood_options.index(current_mood) if current_mood in mood_options else 0
    dropdown.set_selected(idx)
    dropdown.connect(
        "notify::selected",
        _make_handler(filename, mood_options, mood_names, editor, on_change, strip, invalidate_fn),
    )
    overlay.add_overlay(dropdown)

    # Filename label
    name_lbl = Gtk.Label(label=filename)
    name_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    name_lbl.set_max_width_chars(14)
    name_lbl.add_css_class("caption")

    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    inner.append(strip)
    inner.append(overlay)
    inner.append(name_lbl)

    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_valign(Gtk.Align.START)
    frame.set_halign(Gtk.Align.START)
    frame.set_child(inner)
    return frame, picture


def _make_handler(
    filename: str,
    mood_options: list[str],
    mood_names: list[str],
    editor,
    on_change: Callable,
    strip: Gtk.Box,
    invalidate_fn: Callable,
) -> Callable:
    def handler(dropdown: Gtk.DropDown, _param) -> None:
        i = dropdown.get_selected()
        mood = None if i == 0 else mood_options[i]
        editor.set_media_assignment(filename, mood)
        _apply_strip_color(strip, mood, mood_names)
        on_change()
        invalidate_fn()   # re-evaluate filter so tile hides if needed
    return handler


# ---------------------------------------------------------------------------
# Lightbox helpers
# ---------------------------------------------------------------------------

_ANIMATED_EXTS = {".gif", ".webm", ".mp4", ".m4v", ".mov", ".avi", ".mkv"}


def _open_lightbox(path: Path, root: Gtk.Widget) -> None:
    """Open a modal viewer for an image or animated file (GIF / WebM / video).
    GIFs and video formats are routed through _open_animated_lightbox so they
    actually play rather than showing a static frame."""
    if path.suffix.lower() in _ANIMATED_EXTS:
        _open_animated_lightbox(path, root)
        return

    win = Gtk.Window(title=path.name)
    win.set_default_size(900, 700)
    win.set_modal(True)
    if root:
        win.set_transient_for(root)
    picture = Gtk.Picture.new_for_filename(str(path))
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_can_shrink(True)
    picture.set_vexpand(True)
    picture.set_hexpand(True)
    click = Gtk.GestureClick.new()
    click.connect("pressed", lambda *_: win.close())
    picture.add_controller(click)
    key = Gtk.EventControllerKey.new()
    key.connect("key-pressed",
                lambda _c, kv, *_: win.close() or True if kv == Gdk.KEY_Escape else False)
    win.add_controller(key)
    win.set_child(picture)
    win.present()


def _open_animated_lightbox(path: Path, root: Gtk.Widget) -> None:
    """Lightbox for GIFs and video files. Uses Gtk.MediaFile so playback starts
    reliably regardless of whether the widget is already mapped."""
    win = Gtk.Window(title=path.name)
    win.set_default_size(900, 640)
    win.set_modal(True)
    if root:
        win.set_transient_for(root)

    media = Gtk.MediaFile.new_for_filename(str(path))

    video = Gtk.Video(media_stream=media)
    video.set_loop(False)
    video.set_vexpand(True)
    video.set_hexpand(True)

    # Explicit play() after the window is shown; set_autoplay fires before map
    # and is unreliable for files that need GStreamer negotiation.
    def _on_realize(_w):
        media.play()
    video.connect("realize", _on_realize)

    key = Gtk.EventControllerKey.new()
    key.connect("key-pressed",
                lambda _c, kv, *_: (win.close(), True)[1] if kv == Gdk.KEY_Escape else False)
    win.add_controller(key)
    win.set_child(video)
    win.present()


def _open_video_lightbox(path: Path, root: Gtk.Widget) -> None:
    """Entry point for video-tab tiles — delegates to the unified animated lightbox."""
    _open_animated_lightbox(path, root)


# ---------------------------------------------------------------------------
# Audio play/pause
# ---------------------------------------------------------------------------

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

    bus = player.get_bus()
    bus.add_signal_watch()
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


# ---------------------------------------------------------------------------
# Async thumbnail loader
# ---------------------------------------------------------------------------

def _load_thumbnails(pending: list[tuple[Gtk.Picture, Path]]) -> None:
    from PIL import Image
    for picture, path in pending:
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((TILE_W, TILE_H), Image.LANCZOS)
            w, h = img.size
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                img.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4,
            )
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            GLib.idle_add(picture.set_paintable, texture)
        except Exception:
            pass
