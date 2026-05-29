from gi import require_version
require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

_main_window = None


def toast(message: str) -> None:
    if _main_window:
        _main_window._show_toast(message)


def name_popover(anchor: Gtk.Widget, title: str, on_ok: callable) -> None:
    if _main_window:
        _main_window._show_name_popover(anchor, title, on_ok)
