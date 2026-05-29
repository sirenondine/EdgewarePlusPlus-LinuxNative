import ast
import json
import logging
import os

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config import load_default_config
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
from config.gtk_window.tabs.tutorial import open_tutorial
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


class ConfigWindow(Gtk.Window):
    def __init__(self) -> None:
        global config, vars
        super().__init__(title="Edgeware++ Config")
        self.set_default_size(740, 900)
        self.set_size_request(640, 600)

        try:
            self.set_icon_from_file(str(CustomAssets.config_icon()))
        except Exception:
            logging.warning("failed to set icon.")

        css = Gtk.CssProvider()
        css.load_from_string("""
            .save-bar button { font-weight: bold; min-height: 36px; }
            .config-section { border: 1px solid @borders; border-radius: 6px; }
            .config-section-title {
                font-weight: bold; font-size: 1.1em;
                padding: 4px 0; margin: 0 4px;
            }
            .config-toggle { padding: 4px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vars = Vars(config)

        local_version = default_config["versionplusplus"]
        live_version = get_live_version()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        notebook.set_tab_pos(Gtk.PositionType.LEFT)
        vbox.append(notebook)

        general_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        general_tab.set_hexpand(True)
        general_tab.set_vexpand(True)
        general_notebook = Gtk.Notebook()
        general_notebook.set_hexpand(True)
        general_notebook.set_vexpand(True)
        general_tab.append(general_notebook)
        notebook.append_page(general_tab, Gtk.Label(label="General"))

        general_notebook.append_page(
            StartTab(vars, local_version, live_version, pack), Gtk.Label(label="Start")
        )
        general_notebook.append_page(InfoTab(pack), Gtk.Label(label="Pack Info"))
        general_notebook.append_page(
            DefaultFileTab(), Gtk.Label(label="Change Default Files")
        )

        annoyance_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        annoyance_tab.set_hexpand(True)
        annoyance_tab.set_vexpand(True)
        annoyance_notebook = Gtk.Notebook()
        annoyance_notebook.set_hexpand(True)
        annoyance_notebook.set_vexpand(True)
        annoyance_tab.append(annoyance_notebook)
        notebook.append_page(annoyance_tab, Gtk.Label(label="Annoyance/Runtime"))

        annoyance_notebook.append_page(
            PopupTypesTab(vars), Gtk.Label(label="Popup Types")
        )
        annoyance_notebook.append_page(
            PopupTweaksTab(vars), Gtk.Label(label="Popup Tweaks")
        )
        annoyance_notebook.append_page(
            WallpaperTab(vars, pack), Gtk.Label(label="Wallpaper")
        )
        annoyance_notebook.append_page(MoodsTab(pack), Gtk.Label(label="Moods"))
        annoyance_notebook.append_page(BooruTab(vars), Gtk.Label(label="Booru"))
        annoyance_notebook.append_page(
            DangerousSettingsTab(vars), Gtk.Label(label="Dangerous")
        )

        notebook.append_page(BasicModesTab(vars), Gtk.Label(label="Modes"))
        notebook.append_page(
            CorruptionModeTab(vars, pack), Gtk.Label(label="Corruption")
        )
        notebook.append_page(
            TroubleshootingTab(vars, pack), Gtk.Label(label="Troubleshooting")
        )

        tutorial_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        notebook.append_page(tutorial_tab, Gtk.Label(label="Tutorial"))
        self._tutorial_tab_index = notebook.get_n_pages() - 1
        notebook.connect("switch-page", self._on_tab_switch)

        pack_frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vbox.append(pack_frame)

        import_btn = Gtk.Button(label="Import New Pack")
        import_btn.set_hexpand(True)
        import_btn.connect("clicked", lambda _: self._import_window())
        pack_frame.append(import_btn)

        switch_btn = Gtk.Button(label="Switch Pack")
        switch_btn.set_hexpand(True)
        switch_btn.connect("clicked", lambda _: self._switch_window(vars))
        pack_frame.append(switch_btn)

        save_btn = Gtk.Button(label="Save & Exit")
        save_btn.set_hexpand(True)
        save_btn.add_css_class("suggested-action")
        save_btn.add_css_class("save-bar")
        save_btn.connect("clicked", lambda _: write_save(vars, True))
        vbox.append(save_btn)

        if live_version and local_version.split("_")[0] != live_version.split("_")[0] and not (
            local_version.endswith("DEV") or config["toggleInternet"]
        ):
            dialog = Gtk.Dialog(title="Update Available")
            dialog.add_button("OK", Gtk.ResponseType.OK)
            dialog.get_content_area().append(Gtk.Label(
                label="Main local version and web version are not the same.\nPlease visit the Github and download the newer files,\nor use the direct download link on the \"Start\" tab.",
                wrap=True, margin=12,
            ))
            dialog.present()
            dialog.run()
            dialog.destroy()

        self.present()

    def _on_tab_switch(self, notebook, page, page_num):
        if page_num == self._tutorial_tab_index:
            open_tutorial(self)
            notebook.set_current_page(self._last_tab)
        else:
            self._last_tab = page_num

    def _switch_window(self, vars):
        Data.PACKS.mkdir(parents=True, exist_ok=True)
        pack_list = os.listdir(Data.PACKS)

        dialog = Gtk.Window(title="Switch Pack")
        dialog.set_default_size(275, 340)
        dialog.set_transient_for(self)
        dialog.set_modal(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        dialog.set_child(vbox)

        lbl = Gtk.Label(label=f"Currently loaded pack:\n{vars.pack_path.get()}", wrap=True)
        vbox.append(lbl)

        string_list = Gtk.StringList.new(pack_list)
        dropdown = Gtk.DropDown(model=string_list)
        vbox.append(dropdown)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.append(btn_box)

        switch_btn = Gtk.Button(label="Switch")
        def on_switch(_b):
            idx = dropdown.get_selected()
            if 0 <= idx < len(pack_list):
                self._switch_pack(vars, pack_list[idx])
        switch_btn.connect("clicked", on_switch)
        btn_box.append(switch_btn)

        default_btn = Gtk.Button(label="Default")
        default_btn.connect("clicked", lambda _: self._switch_pack(vars, "default"))
        btn_box.append(default_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: dialog.destroy())
        btn_box.append(cancel_btn)

        dialog.present()

    def _switch_pack(self, vars, pack_name):
        vars.pack_path.set(pack_name)
        write_save(vars)
        refresh()

    def _import_window(self):
        dialog = Gtk.Window(title="Import New Pack")
        dialog.set_default_size(350, 225)
        dialog.set_transient_for(self)
        dialog.set_modal(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        dialog.set_child(vbox)

        message = (
            "Would you like to import a new pack, or change the default pack instead?\n\n"
            "Importing a new pack saves it to /data/packs, and allows fast switching "
            "between all packs saved this way.\n\n"
            "Changing the default pack saves it to /resource, overwriting any pack "
            "previously saved there."
        )
        lbl = Gtk.Label(label=message, wrap=True)
        vbox.append(lbl)

        import_new_btn = Gtk.Button(label="Import New")
        import_new_btn.connect("clicked", lambda _: import_pack(False))
        vbox.append(import_new_btn)

        change_default_btn = Gtk.Button(label="Change Default")
        change_default_btn.connect("clicked", lambda _: import_pack(True))
        vbox.append(change_default_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: dialog.destroy())
        vbox.append(cancel_btn)

        dialog.present()
