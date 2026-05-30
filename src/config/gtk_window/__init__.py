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
        self.set_default_size(740, 900)
        self.set_size_request(640, 600)

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
        self.set_content(toolbar_view)

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

        # Sidebar
        sidebar_list = Gtk.ListBox()
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar_list.add_css_class("navigation-sidebar")
        for name in all_page_names:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_margin_start(12)
            lbl.set_margin_end(12)
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(8)
            row.set_child(lbl)
            sidebar_list.append(row)

        sidebar_list.select_row(sidebar_list.get_row_at_index(0))

        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(140)
        split.set_max_sidebar_width(200)
        split.set_sidebar_width_fraction(0.28)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar_list)
        sidebar_nav = Adw.NavigationPage.new(sidebar_scroll, "Settings")
        split.set_sidebar(sidebar_nav)

        self._overlay = Gtk.Overlay()
        self._overlay.set_child(self._stack)
        self._content_nav = Adw.NavigationPage.new(self._overlay, all_page_names[0])
        split.set_content(self._content_nav)

        def on_row_selected(_lb, row):
            if row is None:
                return
            name = all_page_names[row.get_index()]
            self._stack.set_visible_child_name(name)
            self._content_nav.set_title(name)
            split.set_show_content(True)

        sidebar_list.connect("row-selected", on_row_selected)
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
        # Save new pack path to config and disk
        self._vars.pack_path.set(pack_name if pack_name != "default" else "")
        write_save(self._vars, exit_at_end=False)

        # Load new pack
        self._pack = _load_pack(pack_name)
        _ensure_mood_file(self._pack)

        # Rebuild only pack-dependent pages
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

        # Keep the current visible page if it's a static page; otherwise go to Pack Info
        visible = self._stack.get_visible_child_name()
        if visible in _PACK_PAGE_NAMES:
            self._stack.set_visible_child_name("Packs")
            self._content_nav.set_title("Packs")

        # Update window chrome
        self._base_title = f"Edgeware++ Config — {self._pack.info.name}"
        self.set_title(self._base_title)
        self._header_title.set_title("Edgeware++ Config")
        self._header_title.set_subtitle(self._pack.info.name)
        self._dirty = False

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
        if keyval == Gdk.KEY_s and (state & Gdk.ModifierType.CONTROL_MASK):
            write_save(self._vars, False)
            return True
        return False

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
