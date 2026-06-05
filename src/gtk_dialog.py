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

All functions block by running a nested GLib main loop — callers see a simple
synchronous return value while the UI stays responsive."""

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk


def _get_parent() -> Gtk.Window | None:
    from gi.repository import Gio
    app = Gio.Application.get_default()
    if app:
        return app.get_active_window()
    return None


def ask_yes_no(title: str, message: str, *,
               markup: bool = False,
               heading: str | None = None,
               confirm_label: str = "Yes",
               cancel_label: str = "No",
               destructive: bool = False) -> bool:
    """Show an Adw.AlertDialog; return True if the user confirmed."""
    loop = GLib.MainLoop()
    result = {"ok": False}

    dialog = Adw.AlertDialog(heading=heading or title, body=message)
    if markup:
        dialog.set_body_use_markup(True)
    dialog.add_response("cancel", cancel_label)
    dialog.add_response("confirm", confirm_label)
    if destructive:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def on_response(_dlg, response: str) -> None:
        result["ok"] = (response == "confirm")
        if loop.is_running():
            loop.quit()

    dialog.connect("response", on_response)
    dialog.present(_get_parent())
    loop.run()
    return result["ok"]


def show_info(title: str, message: str, *, heading: str | None = None) -> None:
    """Show an informational Adw.AlertDialog with a single Close button."""
    loop = GLib.MainLoop()

    dialog = Adw.AlertDialog(heading=heading or title, body=message)
    dialog.add_response("close", "Close")
    dialog.set_default_response("close")
    dialog.set_close_response("close")

    dialog.connect("response", lambda _dlg, _r: loop.quit() if loop.is_running() else None)
    dialog.present(_get_parent())
    loop.run()


def ask_password(title: str, message: str) -> str | None:
    """Show an Adw.AlertDialog with a password entry; return text or None on cancel."""
    loop = GLib.MainLoop()
    result = {"text": None}

    dialog = Adw.AlertDialog(heading=title, body=message)

    entry = Gtk.PasswordEntry()
    entry.set_show_peek_icon(True)
    entry.set_margin_top(8)
    dialog.set_extra_child(entry)

    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", "Confirm")
    dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("confirm")
    dialog.set_close_response("cancel")

    def on_response(_dlg, response: str) -> None:
        if response == "confirm":
            result["text"] = entry.get_text()
        if loop.is_running():
            loop.quit()

    dialog.connect("response", on_response)
    dialog.present(_get_parent())
    loop.run()
    return result["text"]
