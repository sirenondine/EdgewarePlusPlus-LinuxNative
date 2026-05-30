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
        import_btn = Gtk.Button()
        import_btn.set_child(Adw.ButtonContent(
            label="Import Pack", icon_name="folder-download-symbolic"))
        import_btn.set_tooltip_text(
            "Import New: copy a .zip pack into data/packs for easy switching.\n"
            "Use the ⋮ menu to change the default pack instead.")
        import_btn.connect("clicked", lambda _: import_pack(False))
        header.pack_start(import_btn)

        import_menu_btn = Gtk.MenuButton()
        import_menu_btn.set_icon_name("view-more-symbolic")
        import_menu_btn.set_tooltip_text("Pack import options")
        import_menu = Gtk.PopoverMenu.new_from_model(self._build_import_menu())
        import_menu_btn.set_popover(import_menu)
        header.pack_start(import_menu_btn)

        switch_btn = Gtk.Button()
        switch_btn.set_child(Adw.ButtonContent(
            label="Switch Pack", icon_name="media-playlist-consecutive-symbolic"))
        switch_btn.set_tooltip_text("Switch to another imported pack.")
        switch_btn.connect("clicked", lambda _: self._switch_popover(vars, switch_btn))
        header.pack_start(switch_btn)

        # Save actions (header end)
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

        # App action for "Change Default Pack" (GMenu needs an action)
        from gi.repository import Gio
        change_default_action = Gio.SimpleAction.new("change-default-pack", None)
        change_default_action.connect("activate", lambda _a, _p: import_pack(True))
        app.add_action(change_default_action)

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

    @staticmethod
    def _build_import_menu():
        from gi.repository import Gio
        menu = Gio.Menu()
        menu.append("Change Default Pack", "app.change-default-pack")
        return menu

    def _switch_popover(self, vars, anchor: Gtk.Button) -> None:
        Data.PACKS.mkdir(parents=True, exist_ok=True)
        pack_list = sorted(os.listdir(Data.PACKS))
        current = vars.pack_path.get() or "default"

        popover = Gtk.Popover()
        popover.set_position(Gtk.PositionType.BOTTOM)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_size_request(220, -1)

        # Header
        hdr = Gtk.Label(label="Switch Pack", xalign=0)
        hdr.add_css_class("heading")
        hdr.set_margin_start(12)
        hdr.set_margin_end(12)
        hdr.set_margin_top(10)
        hdr.set_margin_bottom(6)
        outer.append(hdr)

        outer.append(Gtk.Separator())

        if not pack_list:
            msg = Gtk.Label(label="No packs in data/packs.\nImport a pack first.",
                            wrap=True, xalign=0)
            msg.set_margin_start(12); msg.set_margin_end(12)
            msg.set_margin_top(10); msg.set_margin_bottom(10)
            msg.add_css_class("dim-label")
            outer.append(msg)
        else:
            lb = Gtk.ListBox()
            lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
            lb.add_css_class("boxed-list")

            for name in pack_list:
                row = Gtk.ListBoxRow()
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row_box.set_margin_start(12); row_box.set_margin_end(8)
                row_box.set_margin_top(8); row_box.set_margin_bottom(8)
                lbl = Gtk.Label(label=name, xalign=0, hexpand=True)
                row_box.append(lbl)
                if name == current:
                    check = Gtk.Image.new_from_icon_name("object-select-symbolic")
                    check.add_css_class("accent")
                    row_box.append(check)
                row.set_child(row_box)
                lb.append(row)

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_max_content_height(280)
            scroller.set_propagate_natural_height(True)
            scroller.set_child(lb)
            outer.append(scroller)

            def on_row_activated(_lb, row):
                name = pack_list[row.get_index()]
                popover.popdown()
                self._switch_pack(vars, name)

            lb.connect("row-activated", on_row_activated)

        outer.append(Gtk.Separator())

        # Default row at the bottom
        default_row_btn = Gtk.Button(label="Switch to Default Pack")
        default_row_btn.add_css_class("flat")
        default_row_btn.set_margin_start(4); default_row_btn.set_margin_end(4)
        default_row_btn.set_margin_top(4); default_row_btn.set_margin_bottom(4)
        default_row_btn.connect("clicked", lambda _: (popover.popdown(), self._switch_pack(vars, "default")))
        outer.append(default_row_btn)

        popover.set_child(outer)
        popover.set_parent(anchor)
        popover.popup()

    def _switch_pack(self, vars, pack_name):
        vars.pack_path.set(pack_name)
        write_save(vars)
        refresh()
        vbox.append(cancel_btn)

        popover.set_parent(anchor)
        popover.popup()
