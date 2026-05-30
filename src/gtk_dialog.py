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

"""Lightweight GTK4 modal dialog helpers usable from the runtime without
importing the (heavy) config window package.

These run before any application window exists (e.g. the corruption danger
check at startup), so they build self-contained modal windows rather than
Gtk.Dialog, which lays out poorly and looks like a bare toplevel."""

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

_CSS = None


def _ensure_css() -> None:
    global _CSS
    if _CSS is not None:
        return
    from gi.repository import Gdk
    _CSS = Gtk.CssProvider()
    _CSS.load_from_string(".ew-dialog { padding: 18px; }")
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), _CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def _run(window: Gtk.Window) -> None:
    """Show a modal window and block until it closes (nested main loop)."""
    loop = GLib.MainLoop()

    def on_close(_w):
        if loop.is_running():
            loop.quit()
        return False

    window.connect("close-request", on_close)
    window.set_modal(True)
    window.present()
    loop.run()


def _shell(title: str, width: int = 460) -> tuple[Gtk.Window, Gtk.Box]:
    """A titled, centered, non-resizable modal window with a padded content box
    and a button row at the bottom. Returns (window, button_row)."""
    _ensure_css()
    window = Gtk.Window(title=title)
    window.set_resizable(False)
    window.set_default_size(width, -1)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    outer.add_css_class("ew-dialog")
    window.set_child(outer)
    window._content = outer  # subclass-free attach point

    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    buttons.set_halign(Gtk.Align.END)
    window._buttons = buttons
    return window, buttons


def _heading(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class("title-3")
    label.set_xalign(0)
    label.set_wrap(True)
    return label


def ask_yes_no(title: str, message: str, *, markup: bool = False, heading: str | None = None) -> bool:
    window, buttons = _shell(title)
    result = {"ok": False}

    if heading:
        window._content.append(_heading(heading))

    body = Gtk.Label()
    body.set_wrap(True)
    body.set_xalign(0)
    body.set_max_width_chars(54)
    if markup:
        body.set_markup(message)
    else:
        body.set_text(message)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_max_content_height(360)
    scroller.set_propagate_natural_height(True)
    scroller.set_child(body)
    window._content.append(scroller)

    no_btn = Gtk.Button(label="No")
    yes_btn = Gtk.Button(label="Yes")
    yes_btn.add_css_class("destructive-action")
    no_btn.connect("clicked", lambda _: window.close())
    yes_btn.connect("clicked", lambda _: (result.update(ok=True), window.close()))
    buttons.append(no_btn)
    buttons.append(yes_btn)
    window._content.append(buttons)

    _run(window)
    return result["ok"]


def ask_password(title: str, message: str) -> str | None:
    window, buttons = _shell(title, width=380)
    result = {"text": None}

    label = Gtk.Label(label=message)
    label.set_wrap(True)
    label.set_xalign(0)
    window._content.append(label)

    entry = Gtk.PasswordEntry()
    entry.set_show_peek_icon(True)
    window._content.append(entry)

    def confirm():
        result["text"] = entry.get_text()
        window.close()

    cancel_btn = Gtk.Button(label="Cancel")
    confirm_btn = Gtk.Button(label="Confirm")
    confirm_btn.add_css_class("suggested-action")
    cancel_btn.connect("clicked", lambda _: window.close())
    confirm_btn.connect("clicked", lambda _: confirm())
    entry.connect("activate", lambda _: confirm())
    buttons.append(cancel_btn)
    buttons.append(confirm_btn)
    window._content.append(buttons)

    _run(window)
    return result["text"]
