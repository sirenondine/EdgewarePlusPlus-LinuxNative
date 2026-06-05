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

"""A modal thumbnail image picker.

Shows the image files in a directory as a clickable thumbnail grid (plus a
"None" tile). Used to choose a wallpaper / asset by sight rather than typing a
filename. For the modest file counts involved (a pack's root images), thumbnails
load synchronously.
"""

import os
from collections.abc import Callable
from pathlib import Path
from threading import Thread

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

_THUMB = 140
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def list_images(directory: Path) -> list[str]:
    try:
        return sorted(
            f for f in os.listdir(directory)
            if (directory / f).is_file() and Path(f).suffix.lower() in _IMAGE_EXTS
        )
    except Exception:
        return []


def open_image_picker(parent, directory: Path, current: str,
                      on_pick: Callable[[str], None], *,
                      allow_none: bool = True, title: str = "Choose Image") -> None:
    """Open a modal thumbnail grid. Calls on_pick(filename) with the chosen file
    ("" for the None tile) and closes."""
    dialog = Adw.Dialog()
    dialog.set_title(title)
    dialog.set_content_width(640)
    dialog.set_content_height(560)

    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(99)
    flow.set_column_spacing(10)
    flow.set_row_spacing(10)
    flow.set_margin_start(12); flow.set_margin_end(12)
    flow.set_margin_top(12); flow.set_margin_bottom(12)

    def choose(name: str) -> None:
        on_pick(name)
        dialog.close()

    if allow_none:
        flow.append(_tile(None, current, choose))
    for name in list_images(directory):
        flow.append(_tile((directory / name, name), current, choose))

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    scroller.set_child(flow)

    tv = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(title=title, subtitle=str(directory.name)))
    tv.add_top_bar(header)
    tv.set_content(scroller)
    dialog.set_child(tv)
    dialog.present(parent)


def open_remote_image_picker(parent, items: list[tuple[str, str, str]], current: str,
                             on_pick: Callable[[str], None], *,
                             allow_none: bool = True, title: str = "Choose Image") -> None:
    """Like open_image_picker but tiles come from `items` — a list of
    (display_label, value, image_url). Thumbnails download asynchronously.
    on_pick(value) is called with the chosen value ("" for None)."""
    dialog = Adw.Dialog()
    dialog.set_title(title)
    dialog.set_content_width(640)
    dialog.set_content_height(560)

    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(99)
    flow.set_column_spacing(10); flow.set_row_spacing(10)
    flow.set_margin_start(12); flow.set_margin_end(12)
    flow.set_margin_top(12); flow.set_margin_bottom(12)

    def choose(value: str) -> None:
        on_pick(value)
        dialog.close()

    if allow_none:
        flow.append(_url_tile("None", "", None, current, choose))
    for label, value, url in items:
        flow.append(_url_tile(label, value, url, current, choose))

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    scroller.set_child(flow)
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(scroller)
    dialog.set_child(tv)
    dialog.present(parent)


def _url_tile(label: str, value: str, url: "str | None", current: str,
              choose: Callable[[str], None]) -> Gtk.Widget:
    button = Gtk.Button()
    button.add_css_class("flat")
    button.connect("clicked", lambda _b, v=value: choose(v))
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    side = _THUMB * 9 // 16
    frame.set_size_request(_THUMB, side)

    if url is None:
        ph = Gtk.Image.new_from_icon_name("edit-clear-symbolic")
        ph.set_pixel_size(40)
        ph.set_size_request(_THUMB, side)
        ph.add_css_class("dim-label")
        frame.set_child(ph)
    else:
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_size_request(_THUMB, side)
        frame.set_child(picture)
        Thread(target=_load_url_thumb, args=(url, picture), daemon=True).start()

    inner.append(frame)
    lbl = Gtk.Label(label=label)
    lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    lbl.set_max_width_chars(18)
    lbl.add_css_class("caption")
    if value == current or (url is None and not current):
        lbl.add_css_class("accent")
        lbl.set_text("✓ " + label)
    inner.append(lbl)
    button.set_child(inner)
    return button


def _load_url_thumb(url: str, picture: Gtk.Picture) -> None:
    try:
        import requests
        data = requests.get(url, timeout=10).content
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pb = loader.get_pixbuf()
        if pb:
            texture = Gdk.Texture.new_for_pixbuf(pb)
            GLib.idle_add(picture.set_paintable, texture)
    except Exception:
        pass


def _tile(entry, current: str, choose: Callable[[str], None]) -> Gtk.Widget:
    """entry is (path, name) for an image, or None for the 'None' tile."""
    name = "" if entry is None else entry[1]

    button = Gtk.Button()
    button.add_css_class("flat")
    button.connect("clicked", lambda _b, n=name: choose(n))

    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    frame.set_size_request(_THUMB, _THUMB * 9 // 16)

    if entry is None:
        placeholder = Gtk.Image.new_from_icon_name("edit-clear-symbolic")
        placeholder.set_pixel_size(40)
        placeholder.set_size_request(_THUMB, _THUMB * 9 // 16)
        placeholder.add_css_class("dim-label")
        frame.set_child(placeholder)
    else:
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_size_request(_THUMB, _THUMB * 9 // 16)
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(entry[0]), _THUMB, _THUMB, True)
            picture.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
        except Exception:
            pass
        frame.set_child(picture)

    inner.append(frame)

    label = Gtk.Label(label=name or "None")
    label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    label.set_max_width_chars(18)
    label.add_css_class("caption")
    if name == current or (entry is None and not current):
        label.add_css_class("accent")
        label.set_text(("✓ " + (name or "None")))
    inner.append(label)

    button.set_child(inner)
    return button
