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
importing the (heavy) config window package."""

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


def dialog_run(dialog: Gtk.Dialog) -> Gtk.ResponseType:
    """Block on a GTK4 dialog using a nested main loop. Returns the response."""
    loop = GLib.MainLoop()
    result = [Gtk.ResponseType.DELETE_EVENT]

    def on_response(_d, r):
        result[0] = r
        if loop.is_running():
            loop.quit()

    def on_close(_d):
        if loop.is_running():
            loop.quit()
        return False

    dialog.connect("response", on_response)
    dialog.connect("close-request", on_close)
    loop.run()
    return result[0]


def ask_yes_no(title: str, message: str) -> bool:
    dialog = Gtk.Dialog(title=title)
    dialog.add_button("No", Gtk.ResponseType.NO)
    dialog.add_button("Yes", Gtk.ResponseType.YES)
    dialog.get_content_area().append(Gtk.Label(
        label=message, wrap=True,
        margin_start=12, margin_end=12, margin_top=12, margin_bottom=12,
    ))
    dialog.present()
    response = dialog_run(dialog)
    dialog.destroy()
    return response == Gtk.ResponseType.YES


def ask_password(title: str, message: str) -> str | None:
    dialog = Gtk.Dialog(title=title)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Confirm", Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)

    entry = Gtk.PasswordEntry()
    entry.set_show_peek_icon(True)
    entry.set_margin_start(12)
    entry.set_margin_end(12)
    entry.set_margin_top(4)
    entry.set_margin_bottom(8)
    entry.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))

    box = dialog.get_content_area()
    box.append(Gtk.Label(label=message))
    box.append(entry)
    dialog.present()

    response = dialog_run(dialog)
    text = entry.get_text() if response == Gtk.ResponseType.OK else None
    dialog.destroy()
    return text
