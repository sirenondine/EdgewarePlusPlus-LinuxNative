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
from config.gtk_window.import_pack import import_pack
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
from config.gtk_window.utils import config, get_live_version, refresh, write_save
from config.vars import Vars
from pack import Pack
from paths import DEFAULT_PACK_PATH, CustomAssets, Data

config["wallpaperDat"] = ast.literal_eval(config["wallpaperDat"])
default_config = load_default_config()
pack = Pack(
    Data.PACKS / config["packPath"] if config["packPath"] else DEFAULT_PACK_PATH
)

pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

if not pack.info.mood_file.is_file():
    Data.MOODS.mkdir(parents=True, exist_ok=True)
    with open(pack.info.mood_file, "w+") as f:
        f.write(
            json.dumps({"active": list(map(lambda mood: mood.name, pack.index.moods))})
        )

class ConfigWindow(Adw.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        global config, vars
        self._base_title = f"Edgeware++ Config — {pack.info.name}"
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
        local_version = default_config["versionplusplus"]
        live_version = get_live_version()

        self._overlay = Gtk.Overlay()

        # Adwaita chrome: a header bar over the content via a ToolbarView.
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Edgeware++ Config", subtitle=pack.info.name))
        self._header_title = header.get_title_widget()

        # Pack management (header start)
        import_btn = Gtk.Button(label="Import Pack")
        import_btn.set_tooltip_text("Import a new pack or change the default.")
        import_btn.connect("clicked", lambda _: self._import_popover(import_btn))
        header.pack_start(import_btn)

        switch_btn = Gtk.Button(label="Switch Pack")
        switch_btn.set_tooltip_text("Switch to another imported pack.")
        switch_btn.connect("clicked", lambda _: self._switch_popover(vars, switch_btn))
        header.pack_start(switch_btn)

        # Save actions (header end)
        save_exit_btn = Gtk.Button(label="Save & Exit")
        save_exit_btn.add_css_class("suggested-action")
        save_exit_btn.set_tooltip_text("Save settings and close the config window.")
        save_exit_btn.connect("clicked", lambda _: write_save(vars, True))
        header.pack_end(save_exit_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.set_tooltip_text("Save without exiting (Ctrl+S).")
        save_btn.connect("clicked", lambda _: write_save(vars, False))
        header.pack_end(save_btn)

        toolbar_view.add_top_bar(header)
        self.set_content(toolbar_view)

        # --- Responsive split view: sidebar list + page stack ---------------
        pages = [
            ("Start",           StartTab(vars, local_version, live_version, pack)),
            ("Pack Info",       InfoTab(pack)),
            ("Default Files",   DefaultFileTab(pack)),
            ("Popup Types",     PopupTypesTab(vars)),
            ("Popup Tweaks",    PopupTweaksTab(vars)),
            ("Wallpaper",       WallpaperTab(vars, pack)),
            ("Moods",           MoodsTab(pack)),
            ("Booru",           BooruTab(vars)),
            ("Dangerous",       DangerousSettingsTab(vars)),
            ("Modes",           BasicModesTab(vars)),
            ("Corruption",      CorruptionModeTab(vars, pack)),
            ("Troubleshooting", TroubleshootingTab(vars, pack)),
            ("Tutorial",        TutorialTab()),
        ]

        # Content stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        for name, widget in pages:
            self._stack.add_named(widget, name)

        # Sidebar list box
        sidebar_list = Gtk.ListBox()
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar_list.add_css_class("navigation-sidebar")
        for name, _ in pages:
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

        # Sidebar nav page
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar_list)
        sidebar_nav = Adw.NavigationPage.new(sidebar_scroll, "Settings")
        split.set_sidebar(sidebar_nav)

        # Content nav page — wraps the overlay (toast layer) around the stack
        self._overlay = Gtk.Overlay()
        self._overlay.set_child(self._stack)
        self._content_nav = Adw.NavigationPage.new(self._overlay, pages[0][0])
        split.set_content(self._content_nav)

        # Wire selection → stack + title
        def on_row_selected(_lb, row):
            if row is None:
                return
            name, _ = pages[row.get_index()]
            self._stack.set_visible_child_name(name)
            self._content_nav.set_title(name)
            split.set_show_content(True)

        sidebar_list.connect("row-selected", on_row_selected)

        toolbar_view.set_content(split)

        # Ctrl+S shortcut
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self.present()

        # Onboarding — show on first launch or when no pack is loaded
        import sys
        _first_launch = "--first-launch-configure" in sys.argv
        _no_pack = not pack.paths.root.exists() or pack.info.name == "default"
        if _first_launch or _no_pack:
            from config.gtk_window.onboarding import show_onboarding
            GLib.idle_add(lambda: (show_onboarding(self, vars, pack), False)[1])

        # Version update dialog (after present() so window is visible as transient parent)
        if live_version and local_version.split("_")[0] != live_version.split("_")[0] and not (
            local_version.endswith("DEV") or config.get("toggleInternet")
        ):
            from gtk_dialog import ask_yes_no
            if ask_yes_no(
                "Update Available",
                f"A newer version of Edgeware++ LinuxNative is available "
                f"({live_version}). Visit the repository to download it?",
                heading="New version available",
            ):
                import webbrowser
                webbrowser.open("https://github.com/sirenondine/EdgewarePlusPlus-LinuxNative")

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
        self._header_title.set_subtitle(pack.info.name)

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

    def _show_name_popover(self, anchor: Gtk.Widget, title: str, on_ok: callable) -> None:
        entry = Gtk.Entry()
        entry.set_placeholder_text(title)
        entry.set_margin_start(8)
        entry.set_margin_end(8)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        ok_btn = Gtk.Button(label="Save")
        ok_btn.set_use_underline(True)
        ok_btn.add_css_class("suggested-action")
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.set_use_underline(True)
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.append(entry)
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_row.append(ok_btn)
        btn_row.append(cancel_btn)
        vbox.append(btn_row)
        popover.set_child(vbox)
        popover.set_parent(anchor)

        def on_ok_clicked(_b):
            text = entry.get_text().strip()
            if text:
                popover.popdown()
                on_ok(text)

        def on_cancel(_b):
            popover.popdown()

        entry.connect("activate", lambda _e: on_ok_clicked(None))
        ok_btn.connect("clicked", on_ok_clicked)
        cancel_btn.connect("clicked", on_cancel)
        popover.popup()

    def _switch_popover(self, vars, anchor: Gtk.Button) -> None:
        Data.PACKS.mkdir(parents=True, exist_ok=True)
        pack_list = os.listdir(Data.PACKS)

        popover = Gtk.Popover()
        popover.set_position(Gtk.PositionType.TOP)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        popover.set_child(vbox)

        lbl = Gtk.Label(label=f"Current: {vars.pack_path.get()}", wrap=True)
        lbl.set_xalign(0)
        vbox.append(lbl)

        if not pack_list:
            vbox.append(Gtk.Label(label="No packs found in data/packs.\nImport a pack first."))
            popover.set_parent(anchor)
            popover.popup()
            return

        string_list = Gtk.StringList.new(pack_list)
        dropdown = Gtk.DropDown(model=string_list)
        vbox.append(dropdown)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.append(btn_box)

        switch_btn = Gtk.Button(label="_Switch")
        switch_btn.set_use_underline(True)
        def on_switch(_b):
            idx = dropdown.get_selected()
            if 0 <= idx < len(pack_list):
                popover.popdown()
                self._switch_pack(vars, pack_list[idx])
        switch_btn.connect("clicked", on_switch)
        btn_box.append(switch_btn)

        default_btn = Gtk.Button(label="_Default")
        default_btn.set_use_underline(True)
        default_btn.connect("clicked", lambda _: (popover.popdown(), self._switch_pack(vars, "default")))
        btn_box.append(default_btn)

        cancel_btn = Gtk.Button(label="_Cancel")
        cancel_btn.set_use_underline(True)
        cancel_btn.connect("clicked", lambda _: popover.popdown())
        btn_box.append(cancel_btn)

        popover.set_parent(anchor)
        popover.popup()

    def _switch_pack(self, vars, pack_name):
        vars.pack_path.set(pack_name)
        write_save(vars)
        refresh()

    def _import_popover(self, anchor: Gtk.Button) -> None:
        popover = Gtk.Popover()
        popover.set_position(Gtk.PositionType.TOP)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        popover.set_child(vbox)

        message = (
            "Import a new pack or change the default?\n\n"
            "Importing saves to /data/packs for fast switching.\n"
            "Changing default overwrites /resource."
        )
        vbox.append(Gtk.Label(label=message, wrap=True))

        import_new_btn = Gtk.Button(label="_Import New")
        import_new_btn.set_use_underline(True)
        import_new_btn.connect("clicked", lambda _: (popover.popdown(), import_pack(False)))
        vbox.append(import_new_btn)

        change_default_btn = Gtk.Button(label="_Change Default")
        change_default_btn.set_use_underline(True)
        change_default_btn.connect("clicked", lambda _: (popover.popdown(), import_pack(True)))
        vbox.append(change_default_btn)

        cancel_btn = Gtk.Button(label="_Cancel")
        cancel_btn.set_use_underline(True)
        cancel_btn.connect("clicked", lambda _: popover.popdown())
        vbox.append(cancel_btn)

        popover.set_parent(anchor)
        popover.popup()
