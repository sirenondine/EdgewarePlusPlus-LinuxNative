import ast
import json
import logging
import os

from gi import require_version

require_version("Gdk", "4.0")
require_version("Gtk", "4.0")
require_version("Adw", "1")
require_version("Gtk4LayerShell", "1.0")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk

try:
    from gi.repository import Gtk4LayerShell as LayerShell
    _LAYER_OK = LayerShell.is_supported()
except Exception:
    LayerShell = None  # type: ignore[assignment]
    _LAYER_OK = False

from config import load_default_config
from config.gtk_window.toast import toast, name_popover
# Only the (cheap) Home tab is imported eagerly. The settings tabs are imported
# lazily inside the Settings window so the Dashboard, which shows only Home,
# doesn't pay ~170ms loading every settings tab (booru, sextoys, companion, ...).
from config.gtk_window.tabs.home import HomeTab
from config.gtk_window.utils import config, get_live_version, persist
from config.items import CONFIG_DANGER, RESTART_REQUIRED
from config.vars import Vars
from pack import Pack
from paths import DEFAULT_PACK_PATH, CustomAssets, Data

config["wallpaperDat"] = ast.literal_eval(config["wallpaperDat"])
default_config = load_default_config()

pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

# Pages whose widgets depend on the loaded pack — rebuilt on pack switch.
_PACK_PAGE_NAMES = {"General", "Packs", "Assets", "Wallpaper", "Moods", "Corruption", "Troubleshooting"}

# Symbolic icons for the settings sidebar rows (Adwaita icon set).
_SIDEBAR_ICONS = {
    "General": "emblem-system-symbolic",
    "Packs": "folder-symbolic",
    "Assets": "image-x-generic-symbolic",
    "Popup Types": "view-grid-symbolic",
    "Popup Tweaks": "preferences-other-symbolic",
    "Wallpaper": "preferences-desktop-wallpaper-symbolic",
    "Moods": "emblem-favorite-symbolic",
    "Booru": "folder-pictures-symbolic",
    "Sex Toys": "preferences-system-devices-symbolic",
    "Companion": "avatar-default-symbolic",
    "Modes": "applications-games-symbolic",
    "Corruption": "dialog-warning-symbolic",
    "Dangerous": "security-low-symbolic",
    "Gamification": "starred-symbolic",
    "Troubleshooting": "dialog-question-symbolic",
    "Tutorial": "help-about-symbolic",
}

# Sidebar grouping. Rendered as category headers above the first page of each
# group (via ListBox header_func, so page rows stay index-aligned).
_SIDEBAR_CATEGORIES = [
    ("Setup", ["General", "Packs", "Assets"]),
    ("Annoyances", ["Popup Types", "Popup Tweaks", "Wallpaper", "Moods", "Booru"]),
    ("Integrations", ["Sex Toys", "Companion"]),
    ("Advanced", ["Modes", "Corruption", "Dangerous"]),
    ("Progress", ["Gamification"]),
    ("Help", ["Troubleshooting", "Tutorial"]),
]
_PAGE_CATEGORY = {page: cat for cat, pages in _SIDEBAR_CATEGORIES for page in pages}
_CATEGORY_FIRST = {pages[0]: cat for cat, pages in _SIDEBAR_CATEGORIES}


def _make_menu_button() -> Gtk.MenuButton:
    """Hamburger menu button with About / Keyboard Shortcuts / Quit."""
    menu = Gio.Menu()
    menu.append("About Edgeware++", "app.about")
    menu.append("Keyboard Shortcuts", "app.shortcuts")
    sep = Gio.Menu()
    sep.append("Quit", "app.quit")
    menu.append_section(None, sep)
    btn = Gtk.MenuButton()
    btn.set_icon_name("open-menu-symbolic")
    btn.set_menu_model(menu)
    btn.set_tooltip_text("Main menu")
    return btn


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
    if name == "General":
        from config.gtk_window.tabs.general.start import StartTab
        return StartTab(vars, local_version, live_version, pack)
    if name == "Packs":
        from config.gtk_window.tabs.general.info import InfoTab
        return InfoTab(pack, vars, on_switch_pack=on_switch_pack)
    if name == "Assets":
        from config.gtk_window.tabs.general.default_file import DefaultFileTab
        return DefaultFileTab(pack)
    if name == "Wallpaper":
        from config.gtk_window.tabs.annoyance.wallpaper import WallpaperTab
        return WallpaperTab(vars, pack)
    if name == "Moods":
        from config.gtk_window.tabs.annoyance.moods import MoodsTab
        return MoodsTab(pack)
    if name == "Corruption":
        from config.gtk_window.tabs.corruption import CorruptionModeTab
        return CorruptionModeTab(vars, pack)
    if name == "Troubleshooting":
        from config.gtk_window.tabs.troubleshooting import TroubleshootingTab
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


def build_session() -> tuple:
    """Build the shared config state (vars, pack, versions) once so the Dashboard
    and Settings windows operate on the same Vars instance (a single source of
    truth — edits and saves never clobber each other).

    The live version is left blank here and fetched in the background (see
    fetch_live_version_async) — get_live_version() does a blocking network
    request that would otherwise stall the window from appearing."""
    pack_name = config.get("packPath") or "default"
    pack = _load_pack(pack_name)
    _ensure_mood_file(pack)
    vars = Vars(config)
    return vars, pack, default_config["versionplusplus"], ""


def fetch_live_version_async(on_done) -> None:
    """Fetch the latest published version off the main thread; call on_done(str)
    back on the main thread (empty string on failure / when offline)."""
    from threading import Thread

    def work() -> None:
        version = get_live_version()
        GLib.idle_add(lambda: (on_done(version), False)[1])
    Thread(target=work, daemon=True).start()


def maybe_prompt_update(local_version: str, live_version: str) -> None:
    """Offer to open the repo when a newer version is published. Called once per
    process, by whichever window opens first."""
    if live_version and local_version.split("_")[0] != live_version.split("_")[0] and not (
        local_version.endswith("DEV") or config.get("toggleInternet")
    ):
        from gtk_dialog import ask_yes_no
        if ask_yes_no(
            "Update Available",
            f"A newer version of Edgeware++ LinuxNative is available "
            f"({live_version}). Visit the repository to download it?",
            heading="New version available",
            confirm_label="Visit Repository",
            cancel_label="Not Now",
        ):
            import webbrowser
            webbrowser.open("https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative")


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app: Gtk.Application, vars: Vars, pack: Pack,
                 local_version: str, live_version: str, *, on_pack_changed=None,
                 embedded: bool = False) -> None:
        self._pack = pack
        self._on_pack_changed = on_pack_changed
        self._embedded = embedded

        self._base_title = f"Edgeware++ Settings — {self._pack.info.name}"
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

        from config.gtk_window.utils import _ensure_config_css
        _ensure_config_css()

        self._vars = vars
        self._local_version = local_version
        self._live_version = live_version

        # Live autosave + inline danger confirmation. Every change persists
        # (debounced); flipping a setting into a dangerous value first asks for
        # confirmation via the inline bar (see _on_var_change).
        self._known = {key: var.get() for key, var in vars.entries.items()}
        self._save_source = None
        self._suppress = False
        self._danger_pending = None
        for key, var in vars.entries.items():
            var.trace_add(lambda value, k=key: self._on_var_change(k, value))

        # Adwaita chrome
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Edgeware++ Settings", subtitle=self._pack.info.name))
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
        # Menu button rightmost in end area (pack_end first = rightmost).
        # Only shown in standalone mode; embedded mode uses the Dashboard's header.
        if not self._embedded:
            header.pack_end(_make_menu_button())

        # No Save button: settings autosave live (see _on_var_change).
        # When embedded inside the dashboard the dashboard already has a header;
        # skip adding ours so there is no double header bar.
        if not self._embedded:
            toolbar_view.add_top_bar(header)

        # Persistent banner shown when a changed setting needs a restart to take
        # effect (only while a runtime is actually running). Stays until the
        # user dismisses it, so it can't be missed.
        self._restart_banner = Adw.Banner(
            title="Restart Edgeware to apply some changes.")
        self._restart_banner.set_button_label("Dismiss")
        self._restart_banner.connect(
            "button-clicked", lambda _b: self._restart_banner.set_revealed(False))
        self._restart_banner.set_revealed(False)
        toolbar_view.add_top_bar(self._restart_banner)

        # Root overlay covers the entire window (header + content) for the
        # loading screen. Toast overlay (self._overlay) stays inside the stack.
        self._root_overlay = Gtk.Overlay()
        self._root_overlay.set_child(toolbar_view)
        self.set_content(self._root_overlay)

        # --- Responsive split view: sidebar list + lazily-built page stack ---
        # Pages are built the first time they are shown, so opening Settings does
        # not construct all ~16 tabs at once (that was the visible hitch). A
        # background idle backfills the rest, so search has a full index and
        # later clicks are instant. Tab modules are imported here (not at module
        # top) so opening only the Dashboard never loads the heavier tabs.
        from config.gtk_window.tabs.annoyance.booru import BooruTab
        from config.gtk_window.tabs.annoyance.dangerous_settings import DangerousSettingsTab
        from config.gtk_window.tabs.annoyance.popup_tweaks import PopupTweaksTab
        from config.gtk_window.tabs.annoyance.popup_types import PopupTypesTab
        from config.gtk_window.tabs.annoyance.sextoys import SexToysTab
        from config.gtk_window.tabs.companion import CompanionTab
        from config.gtk_window.tabs.modes import BasicModesTab
        from config.gtk_window.tabs.progress import ProgressTab
        from config.gtk_window.tabs.tutorial import TutorialTab

        def _pack_builder(page_name):
            # self._pack is read at build time, so a pack switch is picked up.
            return lambda: _make_pack_page(
                page_name, vars, self._pack,
                self._local_version, self._live_version, self.reload_pack)

        self._page_builders = {
            "General": _pack_builder("General"),
            "Packs": _pack_builder("Packs"),
            "Assets": _pack_builder("Assets"),
            "Wallpaper": _pack_builder("Wallpaper"),
            "Moods": _pack_builder("Moods"),
            "Corruption": _pack_builder("Corruption"),
            "Troubleshooting": _pack_builder("Troubleshooting"),
            "Popup Types": lambda: PopupTypesTab(vars),
            "Popup Tweaks": lambda: PopupTweaksTab(vars),
            "Booru": lambda: BooruTab(vars),
            "Sex Toys": lambda: SexToysTab(vars),
            "Companion": lambda: CompanionTab(vars),
            "Modes": lambda: BasicModesTab(vars),
            "Dangerous": lambda: DangerousSettingsTab(vars),
            "Gamification": lambda: ProgressTab(vars),
            "Tutorial": lambda: TutorialTab(),
        }
        self._built_pages: dict = {}
        self._search_index = None  # built after backfill, or on demand by search

        # Full ordered page list
        all_page_names = [
            "General", "Packs", "Assets",
            "Popup Types", "Popup Tweaks",
            "Wallpaper", "Moods", "Booru", "Sex Toys", "Companion",
            "Modes", "Corruption", "Dangerous",
            "Gamification", "Troubleshooting", "Tutorial",
        ]

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Search results page (added to stack, not in sidebar)
        self._search_page = _SearchResultsPage()
        self._stack.add_named(self._search_page, "__search__")

        # Build only the landing page up front; the rest are lazy.
        self._ensure_page(all_page_names[0])
        self._stack.set_visible_child_name(all_page_names[0])

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
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            icon = Gtk.Image.new_from_icon_name(
                _SIDEBAR_ICONS.get(name, "application-x-executable-symbolic"))
            box.append(icon)
            lbl = Gtk.Label(label=name, xalign=0)
            box.append(lbl)
            row.set_child(box)
            sidebar_list.append(row)
            self._sidebar_rows.append(row)

        # Category headers above the first page of each group.
        def _sidebar_header(row, _before):
            name = all_page_names[row.get_index()]
            cat = _CATEGORY_FIRST.get(name)
            if cat is None:
                row.set_header(None)
                return
            label = Gtk.Label(label=cat, xalign=0)
            label.add_css_class("dim-label")
            label.add_css_class("caption-heading")
            label.set_margin_start(12)
            label.set_margin_end(12)
            label.set_margin_top(12)
            label.set_margin_bottom(4)
            row.set_header(label)
        sidebar_list.set_header_func(_sidebar_header)

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

        # ToastOverlay wraps the stack so Adw.Toasts appear over content.
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._stack)
        self._overlay = Gtk.Overlay()
        self._overlay.set_child(self._toast_overlay)
        self._content_nav = Adw.NavigationPage.new(self._overlay, all_page_names[0])
        split.set_content(self._content_nav)
        self._split = split

        def on_row_selected(_lb, row):
            if row is None:
                return
            name = all_page_names[row.get_index()]
            self._ensure_page(name)
            self._stack.set_visible_child_name(name)
            self._content_nav.set_title(name)
            split.set_show_content(True)

        sidebar_list.connect("row-selected", on_row_selected)

        # Responsive collapse via Adw.Breakpoint: collapses the split view when
        # the window is narrower than 540sp, restores it when wider again.
        _bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 540sp"))
        _bp.connect("apply", lambda _: split.set_collapsed(True))
        _bp.connect("unapply", lambda _: split.set_collapsed(False))
        self.add_breakpoint(_bp)

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
                    self._ensure_page(name)
                    self._stack.set_visible_child_name(name)
                    self._content_nav.set_title(name)
                return
            # Search needs every page's rows; build any not yet backfilled.
            if self._search_index is None:
                self._ensure_all_pages()
                self._rebuild_search_index()
            results = [
                (tab, title, sub) for tab, title, sub in self._search_index
                if query in tab.lower() or query in title.lower() or query in sub.lower()
            ]
            self._search_page.show_results(results, self.navigate_to)
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
        # Kept so _navigate_to (e.g. Home's buttons, search results) can sync
        # the sidebar selection to the page it jumps to.
        self._sidebar_list = sidebar_list
        self._all_page_names = all_page_names

        toolbar_view.set_content(split)

        # Inline danger confirmation: a popover anchored to the control that was
        # changed (built in _begin_danger), not a separate dialog.
        self._confirm_popover = Gtk.Popover()
        self._confirm_popover.set_child(self._build_confirm_bar())
        self._confirm_popover.connect("closed", self._on_confirm_closed)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self.connect("close-request", self._on_close_request)

        # When embedded (content reparented into the Dashboard's stack), don't
        # present this window — it would float as an empty frame over the panel.
        if not self._embedded:
            self.present()

            import sys
            _first_launch = "--first-launch-configure" in sys.argv
            _no_pack = not self._pack.paths.root.exists() or self._pack.info.name == "default"
            if _first_launch or _no_pack:
                from config.gtk_window.onboarding import show_onboarding
                GLib.idle_add(lambda: (show_onboarding(self, vars, self._pack), False)[1])

    # ------------------------------------------------------------------
    # Lazy page building.
    def _ensure_page(self, name: str) -> Gtk.Widget:
        """Build and register a page the first time it is needed."""
        widget = self._built_pages.get(name)
        if widget is None:
            widget = self._page_builders[name]()
            self._built_pages[name] = widget
            self._stack.add_named(widget, name)
        return widget

    def _ensure_all_pages(self) -> None:
        for name in self._all_page_names:
            self._ensure_page(name)

    def _rebuild_search_index(self) -> None:
        self._search_index = _build_search_index(
            [(n, self._built_pages.get(n)) for n in self._all_page_names])

    # ------------------------------------------------------------------
    # Live autosave + inline danger confirmation.
    def _build_confirm_bar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        box.set_size_request(280, -1)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        icon.add_css_class("warning")
        icon.set_valign(Gtk.Align.START)
        head.append(icon)
        self._confirm_label = Gtk.Label(xalign=0, wrap=True, hexpand=True, max_width_chars=34)
        head.append(self._confirm_label)
        box.append(head)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self._resolve_danger(False))
        buttons.append(cancel)
        enable = Gtk.Button(label="Enable anyway")
        enable.add_css_class("destructive-action")
        enable.connect("clicked", lambda _b: self._resolve_danger(True))
        buttons.append(enable)
        box.append(buttons)
        return box

    def _on_var_change(self, key: str, value) -> None:
        if self._suppress:
            return
        old = self._known.get(key)
        # Ignore no-op "changes" — e.g. a lazily-built widget calling set_active
        # with the already-stored value fires notify without a real edit.
        if value == old:
            return
        danger = CONFIG_DANGER.get(key)
        # Flipping a setting INTO a dangerous value asks first, inline — unless
        # the user turned off "Warn if Dangerous Settings Active".
        if (danger and self._vars.safe_mode.get()
                and danger.check(value) and not danger.check(old)):
            self._begin_danger(key, old, value, danger)
            return
        # Retreating from a still-pending dangerous value cancels the prompt.
        if self._danger_pending and self._danger_pending[0] == key:
            self._danger_pending = None
            self._confirm_popover.popdown()
        self._commit(key, value)

    def _begin_danger(self, key: str, old, new, danger) -> None:
        # Only one pending at a time: revert any prior unconfirmed change.
        if self._danger_pending and self._danger_pending[0] != key:
            pk, po, _pn = self._danger_pending
            self._suppress = True
            self._vars.entries[pk].set(po)
            self._suppress = False
        self._danger_pending = (key, old, new)
        level = danger.level.value.capitalize()
        self._confirm_label.set_text(f"{level} risk: {danger.warning or key}")
        # Anchor the popover to the control that changed (fallback: the window).
        anchor = getattr(self._vars.entries[key], "widget", None) or self
        if self._confirm_popover.get_parent() is not anchor:
            if self._confirm_popover.get_parent() is not None:
                self._confirm_popover.unparent()
            self._confirm_popover.set_parent(anchor)
        self._confirm_popover.popup()

    def _resolve_danger(self, accept: bool) -> None:
        if not self._danger_pending:
            self._confirm_popover.popdown()
            return
        key, old, new = self._danger_pending
        self._danger_pending = None
        self._confirm_popover.popdown()
        if accept:
            self._commit(key, new)
        else:
            self._suppress = True
            self._vars.entries[key].set(old)
            self._suppress = False
            self._known[key] = old

    def _on_confirm_closed(self, _popover) -> None:
        # Dismissed by clicking away (not via the buttons) == cancel.
        if self._danger_pending:
            self._resolve_danger(False)

    def _schedule_save(self) -> None:
        if self._save_source is not None:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(300, self._flush_save)

    def _flush_save(self) -> bool:
        self._save_source = None
        persist(self._vars)
        return False

    def _commit(self, key: str, value) -> None:
        """Accept a setting change: remember it, schedule the autosave, and warn
        if it won't take effect until Edgeware restarts."""
        self._known[key] = value
        self._schedule_save()
        if key in RESTART_REQUIRED:
            from panic import is_running
            if is_running():
                self._restart_banner.set_revealed(True)

    def _on_close_request(self, _win) -> bool:
        # Cancel any unconfirmed dangerous change, then flush pending writes.
        if self._danger_pending:
            key, old, _new = self._danger_pending
            self._danger_pending = None
            self._suppress = True
            self._vars.entries[key].set(old)
            self._suppress = False
            self._known[key] = old
        if self._save_source is not None:
            GLib.source_remove(self._save_source)
            self._save_source = None
        persist(self._vars)
        # When attached to a dashboard, hide rather than destroy so it can be
        # reused (recreating would stack duplicate autosave callbacks on the
        # vars). Standalone (`edgeware config`), really close so the app quits.
        if self.get_transient_for() is not None:
            self.set_visible(False)
            return True  # veto destroy, keep for reuse
        return False  # allow close → last window gone → app quits

    def reload_pack(self, pack_name: str) -> None:
        """Switch to a different pack in-place — no process restart."""
        from threading import Thread

        # Save immediately (the autosave is debounced; the pack load needs it now)
        self._vars.pack_path.set(pack_name if pack_name != "default" else "")
        persist(self._vars)

        # Show loading overlay — keeps the UI responsive while I/O runs
        self._show_loading(f"Loading {pack_name}…")

        def _load_in_thread():
            new_pack = _load_pack(pack_name)
            _ensure_mood_file(new_pack)
            _auto_import_wallpapers(new_pack)
            GLib.idle_add(lambda: self._finish_reload(new_pack))

        Thread(target=_load_in_thread, daemon=True).start()

    def _show_loading(self, message: str) -> None:
        """Overlay a full-window spinner + label."""
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            return

        # Outer box fills the entire overlay area (halign/valign FILL).
        outer = Gtk.Box()
        outer.set_halign(Gtk.Align.FILL)
        outer.set_valign(Gtk.Align.FILL)
        outer.add_css_class("loading-overlay")

        # Inner box centers the spinner + label within the outer fill.
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.set_halign(Gtk.Align.CENTER)
        inner.set_valign(Gtk.Align.CENTER)
        inner.set_hexpand(True)
        inner.set_vexpand(True)

        spinner = Adw.Spinner()
        spinner.set_size_request(48, 48)
        inner.append(spinner)

        lbl = Gtk.Label(label=message)
        lbl.add_css_class("title-3")
        inner.append(lbl)

        outer.append(inner)
        self._root_overlay.add_overlay(outer)
        self._loading_overlay = outer

    def _hide_loading(self) -> None:
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            self._root_overlay.remove_overlay(self._loading_overlay)
            self._loading_overlay = None

    def _finish_reload(self, new_pack) -> None:
        """Called on main thread after background load completes."""
        visible = self._stack.get_visible_child_name()
        self._pack = new_pack

        # Drop built pack-dependent pages so they rebuild against the new pack
        # the next time they're shown (the builders read self._pack at call time).
        for name in _PACK_PAGE_NAMES:
            old = self._built_pages.pop(name, None)
            if old:
                self._stack.remove(old)
        self._search_index = None  # rows changed; rebuild lazily

        # If we were on a (now-dropped) pack page or search, show the Packs tab.
        if visible in _PACK_PAGE_NAMES or visible == "__search__":
            self._ensure_page("Packs")
            self._stack.set_visible_child_name("Packs")
            self._content_nav.set_title("Packs")

        # Let the Dashboard window (if open) refresh its pack card.
        if self._on_pack_changed:
            self._on_pack_changed(new_pack)

        # Update window chrome
        self._base_title = f"Edgeware++ Settings — {self._pack.info.name}"
        self.set_title(self._base_title)
        self._header_title.set_title("Edgeware++ Settings")
        self._header_title.set_subtitle(self._pack.info.name)
        self._dirty = False

        self._hide_loading()

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.set_title(f"* {self._base_title}")
            self._header_title.set_title("Edgeware++ Settings ●")
            self._header_title.set_subtitle("unsaved changes")

    def clear_dirty(self) -> None:
        self._dirty = False
        self.set_title(self._base_title)
        self._header_title.set_title("Edgeware++ Settings")
        self._header_title.set_subtitle(self._pack.info.name)

    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        # No Ctrl+S — settings autosave live.
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

    def set_live_version(self, version: str) -> None:
        """Hook for the async version fetch. Settings no longer shows the version
        (it lives on the dashboard), so this only keeps the value current."""
        if version:
            self._live_version = version

    def navigate_to(self, tab_name: str) -> None:
        """Navigate to a tab by name and close search. Public so the Dashboard
        window can open Settings at a specific tab."""
        self._search_bar.set_search_mode(False)
        if tab_name in self._page_builders:
            self._ensure_page(tab_name)
        self._stack.set_visible_child_name(tab_name)
        self._content_nav.set_title(tab_name)
        self._split.set_show_content(True)
        # Keep the sidebar selection in sync with the jumped-to page.
        if tab_name in self._all_page_names:
            row = self._sidebar_list.get_row_at_index(self._all_page_names.index(tab_name))
            if row and not row.is_selected():
                self._sidebar_list.select_row(row)

    def _show_toast(self, message: str) -> None:
        # HIG-standard Adw.Toast via the toast overlay.
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self._toast_overlay.add_toast(toast)

    def _show_name_popover(self, anchor: Gtk.Widget, title: str, on_ok,
                           initial: str = "") -> None:
        """A small popover with an entry + Save/Cancel, anchored to a widget.
        Used by name_popover() for tag/wallpaper/blacklist/preset naming."""
        popover = Gtk.Popover()
        popover.set_parent(anchor)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        entry = Gtk.Entry()
        entry.set_placeholder_text(title)
        if initial:
            entry.set_text(initial)
            entry.select_region(0, -1)
        box.append(entry)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        ok_btn = Gtk.Button(label="Save")
        ok_btn.add_css_class("suggested-action")
        btn_row.append(cancel_btn)
        btn_row.append(ok_btn)
        box.append(btn_row)

        popover.set_child(box)

        def commit(*_):
            text = entry.get_text().strip()
            if text:
                popover.popdown()
                on_ok(text)

        entry.connect("activate", commit)
        ok_btn.connect("clicked", commit)
        cancel_btn.connect("clicked", lambda _: popover.popdown())
        popover.popup()
        entry.grab_focus()


class DashboardWindow(Adw.ApplicationWindow):
    """The Home dashboard as its own lightweight window. Settings opens as a
    separate window (lazily), sharing the same Vars/pack session."""

    def __init__(self, app: Gtk.Application, vars: Vars, pack: Pack,
                 local_version: str, live_version: str) -> None:
        super().__init__(application=app, title="Edgeware++")
        self._app = app
        self._vars = vars
        self._pack = pack
        self._local_version = local_version
        self._live_version = live_version
        self._settings_win = None
        self.set_default_size(480, 720)
        self.set_size_request(360, 480)
        try:
            self.set_icon_from_file(str(CustomAssets.config_icon()))
        except Exception:
            logging.warning("failed to set icon.")

        # --- Header bar ---------------------------------------------------
        toolbar = Adw.ToolbarView()
        self._header = Adw.HeaderBar()

        # Menu button rightmost (pack_end first), settings toggle left of it.
        self._header.pack_end(_make_menu_button())
        # Gear button toggles between home and settings stack pages.
        self._settings_toggle = Gtk.ToggleButton(icon_name="preferences-system-symbolic")
        self._settings_toggle.set_tooltip_text("Settings")
        self._settings_toggle.connect("toggled", self._on_settings_toggled)
        self._header.pack_end(self._settings_toggle)
        toolbar.add_top_bar(self._header)

        # --- Main stack: home <-> settings (SLIDE_DOWN / SLIDE_UP) -------
        # SLIDE_DOWN: new page enters from top, old exits to bottom.
        # That gives the "settings slides down from the top" effect.
        self._main_stack = Gtk.Stack()
        self._main_stack.set_transition_duration(300)

        self._toast_overlay = Adw.ToastOverlay()
        self._main_stack.add_named(self._toast_overlay, "home")

        # Settings page: populated lazily on first open.
        self._settings_placeholder = Gtk.Box()
        self._main_stack.add_named(self._settings_placeholder, "settings")
        self._settings_panel_built = False

        toolbar.set_content(self._main_stack)
        self.set_content(toolbar)
        self._install_home()
        self.connect("close-request", self._on_close_request)
        self.present()

    def _on_close_request(self, _win) -> bool:
        # Persist (shared vars capture any settings edits too), then quit the
        # whole app — otherwise the hidden Settings child keeps it alive.
        persist(self._vars)
        self._app.quit()
        return False

    def _install_home(self) -> None:
        """(Re)build the Home view and reflect it in the header: a ViewSwitcher
        when there are multiple views (gamification on), else a plain title."""
        home = HomeTab(self._vars, self._pack, self._local_version, self._live_version,
                       on_navigate=self._open_settings, on_launch=self._launch_runtime)
        self._toast_overlay.set_child(home)
        if home.has_multiple_views:
            self._home_title = Adw.ViewSwitcher(
                stack=home.view_stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        else:
            self._home_title = Adw.WindowTitle(
                title="Edgeware++", subtitle=self._pack.info.name)
        # Only show the home title widget while on the home page (settings
        # replaces it with its own "Settings" title — see _on_settings_toggled).
        if not getattr(self, "_settings_toggle", None) or not self._settings_toggle.get_active():
            self._header.set_title_widget(self._home_title)

    def _show_toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self._toast_overlay.add_toast(toast)

    def refresh_pack(self, new_pack) -> None:
        """Rebuild the Home view after a pack switch in the Settings window."""
        self._pack = new_pack
        self.set_title("Edgeware++")
        self._install_home()

    def set_live_version(self, version: str) -> None:
        """Update the displayed latest-version once the async fetch returns."""
        if version and version != self._live_version:
            self._live_version = version
            self._install_home()

    def _on_settings_toggled(self, btn: Gtk.ToggleButton) -> None:
        """Slide the settings page in (from the top) or back out to home."""
        if btn.get_active():
            if not self._settings_panel_built:
                self._build_settings_panel()
                self._settings_panel_built = True
            # Settings enters from the top → SLIDE_DOWN.
            self._main_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_DOWN)
            self._main_stack.set_visible_child_name("settings")
            # Replace the home ViewSwitcher with a plain Settings title.
            self._header.set_title_widget(
                Adw.WindowTitle(title="Settings", subtitle=self._pack.info.name))
        else:
            # Home returns → settings exits upward → SLIDE_UP.
            self._main_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP)
            self._main_stack.set_visible_child_name("home")
            self._header.set_title_widget(self._home_title)

    def _build_settings_panel(self) -> None:
        """Build the inline settings content (shared Vars) into the stack's
        settings page. Lazy — built on first open."""
        if self._settings_win is None:
            self._settings_win = SettingsWindow(
                self._app, self._vars, self._pack,
                self._local_version, self._live_version,
                on_pack_changed=self.refresh_pack, embedded=True)
            self._settings_win.set_transient_for(self)
            self._settings_win.set_destroy_with_parent(True)

        # Reparent the SettingsWindow's whole content (header + split view) into
        # our settings stack page. The standalone window stays hidden; we drive
        # it as a widget source only.
        settings_content = self._settings_win.get_content()
        if settings_content:
            self._settings_win.set_content(None)
            settings_content.set_vexpand(True)
            settings_content.set_hexpand(True)
            self._main_stack.remove(self._settings_placeholder)
            self._main_stack.add_named(settings_content, "settings")

    def _open_settings(self, tab_name: str = "General") -> None:
        """Reveal the settings page and navigate to `tab_name`."""
        self._settings_toggle.set_active(True)
        if self._settings_win is not None:
            self._settings_win.navigate_to(tab_name)

    def _launch_runtime(self) -> None:
        """Save settings, start the runtime, and quit the GUI. Refuses if a
        runtime is already running (single instance)."""
        from panic import query_status
        if query_status() is not None:
            self._toast_overlay.add_toast(Adw.Toast.new("Edgeware is already running."))
            return
        persist(self._vars)  # flush any unsaved dashboard edits before launching
        import subprocess
        import sys

        from paths import Process
        # --run so the runtime starts directly instead of bouncing back here.
        subprocess.Popen([sys.executable, str(Process.MAIN), "--run"])
        self._app.quit()
