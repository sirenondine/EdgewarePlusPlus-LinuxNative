import ast
import json
import logging
import os

from gi import require_version

require_version("Gdk", "4.0")
require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from config import load_default_config
from config.gtk_window.toast import toast, name_popover
from config.gtk_window.tabs.annoyance.booru import BooruTab
from config.gtk_window.tabs.annoyance.dangerous_settings import DangerousSettingsTab
from config.gtk_window.tabs.annoyance.moods import MoodsTab
from config.gtk_window.tabs.annoyance.popup_tweaks import PopupTweaksTab
from config.gtk_window.tabs.annoyance.popup_types import PopupTypesTab
from config.gtk_window.tabs.annoyance.wallpaper import WallpaperTab
from config.gtk_window.tabs.corruption import CorruptionModeTab
from config.gtk_window.tabs.general.default_file import DefaultFileTab
from config.gtk_window.tabs.general.info import InfoTab
from config.gtk_window.tabs.general.start import StartTab
from config.gtk_window.tabs.modes import BasicModesTab
from config.gtk_window.tabs.troubleshooting import TroubleshootingTab
from config.gtk_window.tabs.tutorial import TutorialTab
from config.gtk_window.utils import config, get_live_version, write_save
from config.vars import Vars
from pack import Pack
from paths import DEFAULT_PACK_PATH, CustomAssets, Data

config["wallpaperDat"] = ast.literal_eval(config["wallpaperDat"])
default_config = load_default_config()

pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

# Pages whose widgets depend on the loaded pack — rebuilt on pack switch.
_PACK_PAGE_NAMES = {"Overview", "Packs", "Assets", "Wallpaper", "Moods", "Corruption", "Troubleshooting"}


def _load_pack(pack_name: str) -> Pack:
    path = Data.PACKS / pack_name if pack_name and pack_name != "default" else DEFAULT_PACK_PATH
    return Pack(path)


def _ensure_mood_file(pack: Pack) -> None:
    if not pack.info.mood_file.is_file():
        Data.MOODS.mkdir(parents=True, exist_ok=True)
        with open(pack.info.mood_file, "w+") as f:
            f.write(json.dumps({"active": [m.name for m in pack.index.moods]}))


def _make_pack_page(name: str, vars: Vars, pack: Pack,
                    local_version: str, live_version: str,
                    on_switch_pack) -> Gtk.Widget:
    if name == "Overview":
        return StartTab(vars, local_version, live_version, pack)
    if name == "Packs":
        return InfoTab(pack, vars, on_switch_pack=on_switch_pack)
    if name == "Assets":
        return DefaultFileTab(pack)
    if name == "Wallpaper":
        return WallpaperTab(vars, pack)
    if name == "Moods":
        return MoodsTab(pack)
    if name == "Corruption":
        return CorruptionModeTab(vars, pack)
    if name == "Troubleshooting":
        return TroubleshootingTab(vars, pack)
    raise ValueError(f"Unknown pack page: {name}")


def _auto_import_wallpapers(pack: Pack) -> None:
    """Populate wallpaperDat from the new pack's root directory.
    Called on every pack switch so the rotating wallpaper list stays
    in sync with the active pack rather than referencing stale paths."""
    import os
    new_dat: dict[str, str] = {}
    try:
        for f in os.listdir(pack.paths.root):
            if f.lower().endswith((".png", ".jpg", ".jpeg")) and f != "wallpaper.png":
                name = f.rsplit(".", 1)[0]
                new_dat[name] = f
    except Exception:
        pass
    config["wallpaperDat"] = new_dat


def _build_search_index(pages: list[tuple[str, Gtk.Widget]]) -> list[tuple[str, str, str]]:
    """Walk all Adw.PreferencesRow children of each page and return
    (tab_name, title, subtitle) tuples for the search index."""
    index = []

    def walk(widget, tab_name):
        if isinstance(widget, Adw.PreferencesRow):
            title = widget.get_title() if hasattr(widget, "get_title") else ""
            subtitle = (widget.get_subtitle()
                        if hasattr(widget, "get_subtitle") else "") or ""
            if title:
                index.append((tab_name, title, subtitle))
        child = widget.get_first_child()
        while child:
            walk(child, tab_name)
            child = child.get_next_sibling()

    for name, page in pages:
        if page:
            walk(page, name)
    return index


class _SearchResultsPage(Adw.PreferencesPage):
    def __init__(self) -> None:
        super().__init__()
        self._group = Adw.PreferencesGroup(title="Search Results")
        self.add(self._group)

    def show_results(self, results: list[tuple[str, str, str]],
                     on_navigate) -> None:
        # Clear old rows
        while True:
            child = self._group.get_first_child()
            if child is None:
                break
            # PreferencesGroup internal structure — remove all ActionRows
            # by re-creating the group
            break
        # Rebuild group by replacing it
        old = self._group
        self.remove(old)
        self._group = Adw.PreferencesGroup(
            title="Search Results",
            description=f"{len(results)} result{'s' if len(results) != 1 else ''} found",
        )
        self.add(self._group)

        if not results:
            empty = Adw.ActionRow(title="No results found.")
            empty.set_sensitive(False)
            self._group.add(empty)
            return

        for tab_name, title, subtitle in results[:50]:
            row = Adw.ActionRow(title=title, subtitle=tab_name)
            row.set_activatable(True)
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda _r, t=tab_name: on_navigate(t))
            self._group.add(row)


class ConfigWindow(Adw.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        global config, vars

        # Load pack inside __init__ so reload_pack can swap it without restart.
        pack_name = config.get("packPath") or "default"
        self._pack = _load_pack(pack_name)
        _ensure_mood_file(self._pack)

        self._base_title = f"Edgeware++ Config — {self._pack.info.name}"
        super().__init__(application=app, title=self._base_title)
        self._dirty = False
        self._loading_overlay = None
        self.set_default_size(740, 900)
        # Keep minimum narrow enough that NavigationSplitView can collapse
        # (~min_sidebar + min_content ≈ 140+360 = 500px triggers collapse).
        self.set_size_request(360, 480)

        try:
            self.set_icon_from_file(str(CustomAssets.config_icon()))
        except Exception:
            logging.warning("failed to set icon.")

        css = Gtk.CssProvider()
        css.load_from_string("""
            .config-section { border: 1px solid @borders; border-radius: 6px; }
            .config-section-title {
                font-weight: bold; font-size: 1.1em;
                padding: 4px 0; margin: 0 4px;
            }
            .config-toggle { padding: 4px; }
            .toast-bar {
                background: rgba(0,0,0,0.8); color: white;
                border-radius: 8px; padding: 8px 16px;
            }
            .version-mismatch { color: @warning_color; font-weight: bold; }
            .loading-overlay {
                background: alpha(@window_bg_color, 0.85);
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vars = Vars(config)
        self._vars = vars
        for var in vars.entries.values():
            var.trace_add(lambda _: self._mark_dirty())
        self._local_version = default_config["versionplusplus"]
        self._live_version = get_live_version()

        # Adwaita chrome
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Edgeware++ Config", subtitle=self._pack.info.name))
        self._header_title = header.get_title_widget()

        # Sidebar toggle (hamburger) — always visible so user can manually
        # collapse the sidebar regardless of window width
        self._sidebar_toggle = Gtk.ToggleButton()
        self._sidebar_toggle.set_icon_name("sidebar-show-symbolic")
        self._sidebar_toggle.set_active(True)  # sidebar visible by default
        self._sidebar_toggle.set_tooltip_text("Toggle sidebar (Ctrl+B)")
        self._sidebar_toggle.connect("toggled", lambda btn: (
            self._split.set_collapsed(not btn.get_active()) if hasattr(self, "_split") else None,
        ))
        header.pack_start(self._sidebar_toggle)

        save_exit_btn = Gtk.Button()
        save_exit_btn.set_child(Adw.ButtonContent(
            label="Save & Exit", icon_name="document-save-symbolic"))
        save_exit_btn.add_css_class("suggested-action")
        save_exit_btn.set_tooltip_text("Save settings and close the config window.")
        save_exit_btn.connect("clicked", lambda _: write_save(vars, True))
        header.pack_end(save_exit_btn)

        save_btn = Gtk.Button()
        save_btn.set_child(Adw.ButtonContent(
            label="Save", icon_name="document-save-symbolic"))
        save_btn.set_tooltip_text("Save without exiting (Ctrl+S).")
        save_btn.connect("clicked", lambda _: write_save(vars, False))
        header.pack_end(save_btn)

        toolbar_view.add_top_bar(header)

        # Root overlay covers the entire window (header + content) for the
        # loading screen. Toast overlay (self._overlay) stays inside the stack.
        self._root_overlay = Gtk.Overlay()
        self._root_overlay.set_child(toolbar_view)
        self.set_content(self._root_overlay)

        # --- Responsive split view: sidebar list + page stack ---------------
        static_pages = [
            ("Popup Types",  PopupTypesTab(vars)),
            ("Popup Tweaks", PopupTweaksTab(vars)),
            ("Booru",        BooruTab(vars)),
            ("Modes",        BasicModesTab(vars)),
            ("Dangerous",    DangerousSettingsTab(vars)),
            ("Tutorial",     TutorialTab()),
        ]

        # Full ordered page list (pack pages built first pass)
        all_page_names = [
            "Overview", "Packs", "Assets",
            "Popup Types", "Popup Tweaks",
            "Wallpaper", "Moods", "Booru",
            "Modes", "Corruption", "Dangerous",
            "Troubleshooting", "Tutorial",
        ]

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Add static pages
        for name, widget in static_pages:
            self._stack.add_named(widget, name)

        # Add pack-dependent pages
        for name in _PACK_PAGE_NAMES:
            widget = _make_pack_page(
                name, vars, self._pack,
                self._local_version, self._live_version,
                self.reload_pack,
            )
            self._stack.add_named(widget, name)

        # Build search index from all preference rows across all pages
        self._search_index = _build_search_index(
            [(n, self._stack.get_child_by_name(n)) for n in all_page_names]
        )

        # Search results page (added to stack, not in sidebar)
        self._search_page = _SearchResultsPage()
        self._stack.add_named(self._search_page, "__search__")

        # Sidebar
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search bar
        search_bar = Gtk.SearchBar()
        search_bar.set_show_close_button(True)
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search settings…")
        search_entry.set_hexpand(True)
        search_bar.set_child(search_entry)
        search_bar.connect_entry(search_entry)
        sidebar_box.append(search_bar)

        # Search toggle button in header
        search_btn = Gtk.ToggleButton()
        search_btn.set_icon_name("system-search-symbolic")
        search_btn.set_tooltip_text("Search settings (Ctrl+F)")
        search_btn.connect("toggled", lambda btn: (
            search_bar.set_search_mode(btn.get_active()),
            search_entry.grab_focus() if btn.get_active() else None,
        ))
        header.pack_start(search_btn)

        sidebar_list = Gtk.ListBox()
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar_list.add_css_class("navigation-sidebar")
        self._sidebar_rows: list[Gtk.ListBoxRow] = []
        for name in all_page_names:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_margin_start(12)
            lbl.set_margin_end(12)
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(8)
            row.set_child(lbl)
            sidebar_list.append(row)
            self._sidebar_rows.append(row)

        sidebar_list.select_row(sidebar_list.get_row_at_index(0))

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_vexpand(True)
        sidebar_scroll.set_child(sidebar_list)
        sidebar_box.append(sidebar_scroll)

        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(140)
        split.set_max_sidebar_width(200)
        split.set_sidebar_width_fraction(0.28)

        sidebar_nav = Adw.NavigationPage.new(sidebar_box, "Settings")
        split.set_sidebar(sidebar_nav)

        self._overlay = Gtk.Overlay()
        self._overlay.set_child(self._stack)
        self._content_nav = Adw.NavigationPage.new(self._overlay, all_page_names[0])
        split.set_content(self._content_nav)
        self._split = split

        def on_row_selected(_lb, row):
            if row is None:
                return
            name = all_page_names[row.get_index()]
            self._stack.set_visible_child_name(name)
            self._content_nav.set_title(name)
            split.set_show_content(True)

        sidebar_list.connect("row-selected", on_row_selected)

        # Responsive collapse: NavigationSplitView does not auto-collapse;
        # drive it manually from window width. Collapse below 540px.
        _COLLAPSE_WIDTH = 540

        # Drive collapse via width property notification (fires on every resize).
        def _on_width_changed(*_):
            w = split.get_width()
            if w > 0:
                split.set_collapsed(w < _COLLAPSE_WIDTH)

        split.connect("notify::width", _on_width_changed)

        # Sync toggle button when collapsed state changes from any source
        def _on_collapsed_changed(s, _p):
            self._sidebar_toggle.set_active(not s.get_collapsed())

        split.connect("notify::collapsed", _on_collapsed_changed)

        # Search logic
        def on_search_changed(entry):
            query = entry.get_text().strip().lower()
            if not query:
                # Show current sidebar tab
                sel = sidebar_list.get_selected_row()
                if sel:
                    name = all_page_names[sel.get_index()]
                    self._stack.set_visible_child_name(name)
                    self._content_nav.set_title(name)
                return
            results = [
                (tab, title, sub) for tab, title, sub in self._search_index
                if query in tab.lower() or query in title.lower() or query in sub.lower()
            ]
            self._search_page.show_results(results, self._navigate_to)
            self._stack.set_visible_child_name("__search__")
            self._content_nav.set_title("Search Results")
            split.set_show_content(True)

        def on_search_stopped(_bar):
            sidebar_list.unselect_all()
            sidebar_list.select_row(sidebar_list.get_row_at_index(0))

        search_entry.connect("search-changed", on_search_changed)
        search_bar.connect("notify::search-mode", lambda b, _p:
            on_search_stopped(b) if not b.get_search_mode() else None)

        # Ctrl+F shortcut — toggle search
        self._search_bar = search_bar
        self._search_entry = search_entry

        toolbar_view.set_content(split)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self.present()

        import sys
        _first_launch = "--first-launch-configure" in sys.argv
        _no_pack = not self._pack.paths.root.exists() or self._pack.info.name == "default"
        if _first_launch or _no_pack:
            from config.gtk_window.onboarding import show_onboarding
            GLib.idle_add(lambda: (show_onboarding(self, vars, self._pack), False)[1])

        if self._live_version and self._local_version.split("_")[0] != self._live_version.split("_")[0] and not (
            self._local_version.endswith("DEV") or config.get("toggleInternet")
        ):
            from gtk_dialog import ask_yes_no
            if ask_yes_no(
                "Update Available",
                f"A newer version of Edgeware++ LinuxNative is available "
                f"({self._live_version}). Visit the repository to download it?",
                heading="New version available",
            ):
                import webbrowser
                webbrowser.open("https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative")

    def reload_pack(self, pack_name: str) -> None:
        """Switch to a different pack in-place — no process restart."""
        from threading import Thread

        # Save immediately (fast, stays on main thread)
        self._vars.pack_path.set(pack_name if pack_name != "default" else "")
        write_save(self._vars, exit_at_end=False)

        # Show loading overlay — keeps the UI responsive while I/O runs
        self._show_loading(f"Loading {pack_name}…")

        def _load_in_thread():
            new_pack = _load_pack(pack_name)
            _ensure_mood_file(new_pack)
            _auto_import_wallpapers(new_pack)
            GLib.idle_add(lambda: self._finish_reload(new_pack))

        Thread(target=_load_in_thread, daemon=True).start()

    def _show_loading(self, message: str) -> None:
        """Overlay a spinner + label over the content area."""
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_hexpand(True)
        box.set_vexpand(True)
        # Dim background
        box.add_css_class("loading-overlay")

        spinner = Adw.Spinner()
        spinner.set_size_request(48, 48)
        box.append(spinner)

        lbl = Gtk.Label(label=message)
        lbl.add_css_class("title-3")
        box.append(lbl)

        self._root_overlay.add_overlay(box)
        self._loading_overlay = box

    def _hide_loading(self) -> None:
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            self._root_overlay.remove_overlay(self._loading_overlay)
            self._loading_overlay = None

    def _finish_reload(self, new_pack) -> None:
        """Called on main thread after background load completes."""
        self._pack = new_pack

        # Rebuild pack-dependent pages
        for name in _PACK_PAGE_NAMES:
            old = self._stack.get_child_by_name(name)
            if old:
                self._stack.remove(old)
            widget = _make_pack_page(
                name, self._vars, self._pack,
                self._local_version, self._live_version,
                self.reload_pack,
            )
            self._stack.add_named(widget, name)

        # Navigate to Packs tab if we were on a pack-dependent page
        visible = self._stack.get_visible_child_name()
        if visible in _PACK_PAGE_NAMES or visible == "__search__":
            self._stack.set_visible_child_name("Packs")
            self._content_nav.set_title("Packs")

        # Update window chrome
        self._base_title = f"Edgeware++ Config — {self._pack.info.name}"
        self.set_title(self._base_title)
        self._header_title.set_title("Edgeware++ Config")
        self._header_title.set_subtitle(self._pack.info.name)
        self._dirty = False

        self._hide_loading()

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.set_title(f"* {self._base_title}")
            self._header_title.set_title("Edgeware++ Config ●")
            self._header_title.set_subtitle("unsaved changes")

    def clear_dirty(self) -> None:
        self._dirty = False
        self.set_title(self._base_title)
        self._header_title.set_title("Edgeware++ Config")
        self._header_title.set_subtitle(self._pack.info.name)

    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_s and ctrl:
            write_save(self._vars, False)
            return True
        if keyval == Gdk.KEY_f and ctrl:
            self._search_bar.set_search_mode(
                not self._search_bar.get_search_mode())
            if self._search_bar.get_search_mode():
                self._search_entry.grab_focus()
            return True
        if keyval == Gdk.KEY_b and ctrl:
            self._sidebar_toggle.set_active(not self._sidebar_toggle.get_active())
            return True
        return False

    def _navigate_to(self, tab_name: str) -> None:
        """Navigate to a tab by name and close search."""
        self._search_bar.set_search_mode(False)
        self._stack.set_visible_child_name(tab_name)
        self._content_nav.set_title(tab_name)
        self._split.set_show_content(True)
        # Select the matching sidebar row
        for i, row in enumerate(self._sidebar_rows):
            lbl = row.get_child()
            if isinstance(lbl, Gtk.Label) and lbl.get_text() == tab_name:
                row.get_parent().select_row(row)
                break

    def _show_toast(self, message: str) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.add_css_class("toast-bar")
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(48)
        lbl = Gtk.Label(label=message)
        box.append(lbl)
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        revealer.set_halign(Gtk.Align.CENTER)
        revealer.set_valign(Gtk.Align.END)
        revealer.set_can_target(False)
        revealer.set_child(box)
        self._overlay.add_overlay(revealer)
        revealer.set_reveal_child(True)

        def hide():
            revealer.set_reveal_child(False)
            GLib.timeout_add_seconds(1, revealer.unparent)
            return False
        GLib.timeout_add_seconds(3, hide)
