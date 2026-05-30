from gi import require_version
require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk, GLib

_main_window = None  # kept for legacy compatibility; prefer _get_window()


def _get_window():
    app = Gio.Application.get_default()
    if app:
        return app.get_active_window()
    return _main_window


def toast(message: str) -> None:
    window = _get_window()
    if window and hasattr(window, "_show_toast"):
        window._show_toast(message)


def name_popover(anchor: Gtk.Widget, title: str, on_ok: callable) -> None:
    window = _get_window()
    if window and hasattr(window, "_show_name_popover"):
        window._show_name_popover(anchor, title, on_ok)
