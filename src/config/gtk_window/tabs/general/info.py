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

import json
import os
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

from pack import Pack
from paths import Data

INFO_TEXT = (
    "Requires an optional \"information file\" that pack creators can add. If this is "
    "greyed out but other sections work, the pack just doesn't have one."
)
DISCORD_TEXT = (
    "Only displays on Discord if you turn on the associated \"Show on Discord\" "
    "setting (Dangerous)."
)


class InfoTab(Gtk.Box):
    """Packs tab. Adw.NavigationView (owned, not subclassed — it's a final GType)
    provides the slide-in-place animation when the pack editor is opened."""

    def __init__(self, pack: Pack, vars=None, on_switch_pack=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._pack = pack
        self._vars = vars
        self._on_switch_pack = on_switch_pack
        # Per-pack-dir editor cache: str(pack_dir) -> (PackEditorContent, NavigationPage)
        self._editor_cache: dict[str, tuple] = {}

        self._nav = Adw.NavigationView()
        self._nav.set_vexpand(True)
        self._nav.set_hexpand(True)
        self.append(self._nav)

        # ---- Main page (pack management + installed list) ----------------
        main_pref = Adw.PreferencesPage()
        self._build_main(main_pref, pack, vars)
        main_page = Adw.NavigationPage.new(main_pref, "Packs")
        self._nav.add(main_page)

        # Flush + refresh when the user navigates back from the editor.
        self._nav.connect("popped", self._on_popped)

    def _build_main(self, page: Adw.PreferencesPage, pack: Pack, vars) -> None:
        # ---- Pack management --------------------------------------------
        mgmt = Adw.PreferencesGroup(title="Pack Management")
        page.add(mgmt)

        current_row = Adw.ActionRow(title="Active Pack", subtitle=pack.info.name)
        current_row.add_prefix(_pack_icon_prefix(pack.paths.root))
        mgmt.add(current_row)

        import_row = Adw.ActionRow(
            title="Import New Pack",
            subtitle="Extract a .zip into data/packs/ for easy switching.",
        )
        import_btn = Gtk.Button()
        import_btn.set_child(Adw.ButtonContent(label="Import…", icon_name="folder-download-symbolic"))
        import_btn.set_valign(Gtk.Align.CENTER)
        import_btn.connect("clicked", lambda _: self._on_import_new())
        import_row.add_suffix(import_btn)
        import_row.set_activatable_widget(import_btn)
        mgmt.add(import_row)

        create_row = Adw.ActionRow(
            title="Create New Pack",
            subtitle="Scaffold an empty pack and open it in the editor.",
        )
        create_btn = Gtk.Button()
        create_btn.set_child(Adw.ButtonContent(label="Create…", icon_name="document-new-symbolic"))
        create_btn.set_valign(Gtk.Align.CENTER)
        create_btn.connect("clicked", lambda _: self._on_create_pack())
        create_row.add_suffix(create_btn)
        create_row.set_activatable_widget(create_btn)
        mgmt.add(create_row)

        from pack.edit import is_writable
        writable = is_writable(pack.paths.root)
        edit_row = Adw.ActionRow(
            title="Edit This Pack",
            subtitle="Change pack info and popup text." if writable
                     else "This pack is read-only and cannot be edited here.",
        )
        edit_btn = Gtk.Button()
        edit_btn.set_child(Adw.ButtonContent(label="Edit…", icon_name="document-edit-symbolic"))
        edit_btn.set_valign(Gtk.Align.CENTER)
        edit_btn.set_sensitive(writable)
        edit_btn.connect("clicked", lambda _: self._on_edit_pack())
        edit_row.add_suffix(edit_btn)
        if writable:
            edit_row.set_activatable_widget(edit_btn)
        mgmt.add(edit_row)

        # ---- AI text generation model ------------------------------------
        # The pack editor's "✨ Generate" buttons use this model (falls back to
        # the companion's main model). Surfaced here so it's selectable right
        # from the Packs screen, not buried in the Companion tab.
        if vars is not None:
            from config.gtk_window.widgets import AdwEntryRow, model_picker

            ai_group = Adw.PreferencesGroup(
                title="AI Text Generation",
                description="Model used by the pack editor's Generate buttons. Uses the "
                            "companion's server and API key; leave blank to use the "
                            "companion's main model.",
            )
            page.add(ai_group)
            ai_group.add(AdwEntryRow("Pack editor model", vars.pack_edit_model))
            ai_group.add(model_picker(
                vars, vars.pack_edit_model,
                subtitle="Detected on the companion's Ollama server"))

        # ---- Pack configuration ------------------------------------------
        if vars is not None:
            from config.gtk_window.widgets import AdwSwitchRow

            config_group = Adw.PreferencesGroup(
                title="Pack Configuration",
                description=(
                    "Pack creators can ship a config file with settings tailored to "
                    "their intended experience for this pack."
                ),
            )
            page.add(config_group)

            load_cfg_row = Adw.ActionRow(
                title="Load Pack Configuration",
                subtitle=f"{len(pack.config)} suggested setting"
                         f"{'s' if len(pack.config) != 1 else ''} in this pack.",
            )
            load_cfg_btn = Gtk.Button(label="Preview & Load…")
            load_cfg_btn.set_valign(Gtk.Align.CENTER)
            load_cfg_btn.set_sensitive(bool(pack.config))
            load_cfg_btn.connect("clicked", lambda _: self._on_load_pack_config())
            load_cfg_row.add_suffix(load_cfg_btn)
            load_cfg_row.set_activatable_widget(load_cfg_btn)
            config_group.add(load_cfg_row)

            config_group.add(AdwSwitchRow(
                "Force Warning Failsafes", vars.preset_danger,
                subtitle=(
                    "Turns on \"Warn if Dangerous Settings Active\" after loading a pack "
                    "config, regardless of the config's own setting."
                )))

        # ---- Installed packs ---------------------------------------------
        pack_dirs = sorted(
            [d for d in Data.PACKS.iterdir() if d.is_dir()],
            key=lambda d: d.name.lower()
        ) if Data.PACKS.exists() else []

        if pack_dirs:
            from config.gtk_window.import_pack import get_default_pack_source
            from pack.edit import is_writable
            switch_group = Adw.PreferencesGroup(
                title="Installed Packs",
                description="Switch activates the pack. Set Default copies it to resource/.",
            )
            page.add(switch_group)

            current_name = vars.pack_path.get() if vars else ""
            self._default_buttons: dict[str, Gtk.Button] = {}

            default_source = get_default_pack_source()

            for pack_dir in pack_dirs:
                name = pack_dir.name
                info = _read_pack_info(pack_dir)
                display_name = info.get("name") or name
                description = info.get("description") or ""

                btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                btn_box.set_valign(Gtk.Align.CENTER)

                sw_btn = Gtk.Button()
                if name == current_name:
                    sw_btn.set_icon_name("object-select-symbolic")
                    sw_btn.add_css_class("accent")
                    sw_btn.set_sensitive(False)
                    sw_btn.set_tooltip_text("Currently active pack")
                else:
                    sw_btn.set_icon_name("media-playback-start-symbolic")
                    sw_btn.set_tooltip_text("Switch to this pack")
                    sw_btn.connect("clicked", lambda _b, n=name: self._on_switch(n))
                btn_box.append(sw_btn)

                set_def_btn = Gtk.Button()
                set_def_btn.connect("clicked", lambda _b, d=pack_dir: self._on_set_default(d))
                btn_box.append(set_def_btn)
                self._default_buttons[name] = set_def_btn
                self._style_default_button(set_def_btn, name == default_source)

                edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
                edit_btn.set_tooltip_text(
                    "Edit pack" if is_writable(pack_dir) else "Pack is read-only")
                edit_btn.set_sensitive(is_writable(pack_dir))
                edit_btn.connect("clicked", lambda _b, d=pack_dir: self._push_editor(d))
                btn_box.append(edit_btn)

                row = _build_pack_row(
                    pack_dir, display_name, description,
                    _pack_feature_tags(pack_dir), btn_box)
                switch_group.add(row)

            default_row = Adw.ActionRow(
                title="Default Pack",
                subtitle="The built-in resource/ pack — no switch needed.",
            )
            def_btn = Gtk.Button(label="Switch")
            def_btn.set_valign(Gtk.Align.CENTER)
            def_btn.connect("clicked", lambda _: self._on_switch("default"))
            default_row.add_suffix(def_btn)
            default_row.set_activatable_widget(def_btn)
            switch_group.add(default_row)

    def _on_load_pack_config(self) -> None:
        from config.gtk_window.preset import apply_preset, compute_diff, show_config_diff
        show_config_diff(
            self.get_root(),
            "Load Pack Configuration",
            f"Suggested settings shipped with {self._pack.info.name}.",
            compute_diff(self._pack.config, self._vars),
            "Apply Pack Config",
            lambda: apply_preset(self._pack.config, self._vars),
        )

    def _on_import_new(self) -> None:
        from config.gtk_window.import_pack import import_pack
        import_pack(False)

    def _on_create_pack(self) -> None:
        # Small modal collecting the new pack's name + creator.
        win = Gtk.Window(title="Create New Pack")
        win.set_default_size(420, 0)
        win.set_modal(True)
        win.set_transient_for(self.get_root())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(16);  box.set_margin_bottom(16)
        win.set_child(box)

        name_row = Adw.EntryRow(title="Pack Name")
        creator_row = Adw.EntryRow(title="Creator")
        group = Adw.PreferencesGroup()
        group.add(name_row); group.add(creator_row)
        box.append(group)

        btn_row = Gtk.Box(spacing=8); btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _: win.close())
        create = Gtk.Button(label="Create")
        create.add_css_class("suggested-action")
        btn_row.append(cancel); btn_row.append(create)
        box.append(btn_row)

        def do_create(_b) -> None:
            from pack.edit import create_pack
            from paths import Data
            pack_dir, err = create_pack(Data.PACKS, name_row.get_text(), creator_row.get_text())
            if err:
                from config.gtk_window.toast import toast
                toast(err)
                return
            win.close()
            self._push_editor(pack_dir)

        create.connect("clicked", do_create)
        win.present()

    def _on_edit_pack(self) -> None:
        self._push_editor(self._pack.paths.root)

    def _push_editor(self, pack_dir: Path) -> None:
        """Build (lazily, cached per pack_dir) and push an editor NavigationPage."""
        from config.gtk_window.pack_editor import PackEditorContent

        key = str(pack_dir)
        if key not in self._editor_cache:
            content = PackEditorContent(pack_dir)

            editor_pref = Adw.PreferencesPage()
            editor_pref.set_vexpand(True)
            content.build_into(
                editor_pref,
                push_page=self._nav.push,
                pop_page=self._nav.pop,
                on_migrated=lambda d=pack_dir: self._rebuild_editor(d),
            )

            back_btn = Gtk.Button()
            back_btn.set_child(Adw.ButtonContent(
                icon_name="go-previous-symbolic", label="Packs"))
            back_btn.set_halign(Gtk.Align.START)
            back_btn.set_margin_start(6)
            back_btn.connect("clicked", lambda _: self._nav.pop())

            top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            top_bar.append(back_btn)

            toolbar_view = Adw.ToolbarView()
            toolbar_view.add_top_bar(top_bar)
            toolbar_view.set_content(editor_pref)

            pack_name = content.editor.get_info("name") or pack_dir.name
            page = Adw.NavigationPage.new(toolbar_view, f"Edit: {pack_name}")
            self._editor_cache[key] = (content, page)

        content, page = self._editor_cache[key]
        self._nav.push(page)

    def _rebuild_editor(self, pack_dir: Path) -> None:
        """Drop the cached editor for `pack_dir`, pop back, and re-push a freshly
        built one. Used after legacy migration so the editor reflects the new
        index.json without reloading the whole window."""
        key = str(pack_dir)
        # Pop to the main packs page (without triggering a config refresh).
        while self._nav.get_navigation_stack().get_n_items() > 1:
            self._nav.pop()
        self._editor_cache.pop(key, None)
        GLib.idle_add(lambda: (self._push_editor(pack_dir), False)[1])

    def _on_popped(self, _nav, page) -> None:
        """Flush the editor that was just popped, refresh if it saved anything."""
        # Reverse-lookup which cached editor owns this page.
        for content, cached_page in self._editor_cache.values():
            if cached_page is page:
                content.flush()
                if content.saved_any:
                    from config.gtk_window.utils import refresh
                    refresh()
                return

    @staticmethod
    def _style_default_button(btn: Gtk.Button, is_default: bool) -> None:
        if is_default:
            btn.set_icon_name("starred-symbolic")
            btn.add_css_class("accent")
            btn.set_tooltip_text("This is the default pack")
        else:
            btn.set_icon_name("non-starred-symbolic")
            btn.remove_css_class("accent")
            btn.set_tooltip_text("Set as default pack (copies to resource/)")

    def _on_set_default(self, pack_dir) -> None:
        from config.gtk_window.import_pack import set_default_from_installed

        def on_done(new_default: str) -> None:
            for name, btn in self._default_buttons.items():
                self._style_default_button(btn, name == new_default)

        set_default_from_installed(pack_dir, on_done=on_done)

    def _on_switch(self, name: str) -> None:
        if self._on_switch_pack:
            self._on_switch_pack(name)


# Feature label -> pill colour, in display order.
_FEATURE_COLORS = {
    "Images": "#3498db", "Videos": "#9b59b6", "Audio": "#1abc9c",
    "Moods": "#e67e22", "Corruption": "#e74c3c", "Companion": "#2ecc71",
    "Config": "#f39c12", "Discord": "#5865f2", "Wallpaper": "#95a5a6",
}


def _dir_has_files(directory: Path) -> bool:
    try:
        return any((directory / f).is_file() for f in os.listdir(directory))
    except Exception:
        return False


def _pack_feature_tags(pack_dir: Path) -> list[str]:
    """Cheaply detect which features a pack ships (no full Pack load)."""
    # Resolve a possible resource/ subdir wrapper (some packs nest content).
    root = pack_dir
    if not (pack_dir / "info.json").is_file() and (pack_dir / "resource").is_dir():
        root = pack_dir / "resource"

    tags: list[str] = []
    if _dir_has_files(root / "img"):
        tags.append("Images")
    if _dir_has_files(root / "vid"):
        tags.append("Videos")
    if _dir_has_files(root / "aud"):
        tags.append("Audio")
    # Moods: modern index.json with >1 mood, or a legacy media.json.
    has_moods = (root / "media.json").is_file()
    if not has_moods and (root / "index.json").is_file():
        try:
            idx = json.loads((root / "index.json").read_text(encoding="utf-8", errors="replace"))
            has_moods = len(idx.get("moods", [])) > 0
        except Exception:
            pass
    if has_moods:
        tags.append("Moods")
    if (root / "corruption.json").is_file():
        tags.append("Corruption")
    if (root / "companion.json").is_file():
        tags.append("Companion")
    if (root / "config.json").is_file():
        tags.append("Config")
    if (root / "discord.dat").is_file():
        tags.append("Discord")
    if (root / "wallpaper.png").is_file():
        tags.append("Wallpaper")
    return tags


def _ensure_tag_css() -> None:
    """Inject rounded-pill CSS (once). One class per feature colour."""
    if getattr(_ensure_tag_css, "_done", False):
        return
    _ensure_tag_css._done = True  # type: ignore[attr-defined]
    parts = [
        b".pack-tag { border-radius: 10px; padding: 1px 9px; margin: 0; "
        b"font-size: 0.78em; font-weight: bold; color: #ffffff; }\n"
    ]
    for color in set(_FEATURE_COLORS.values()) | {"#7f8c8d"}:
        cid = color.lstrip("#")
        parts.append(f".pack-tag-{cid} {{ background-color: {color}; }}\n".encode())
    provider = Gtk.CssProvider()
    provider.load_from_data(b"".join(parts))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _pills_box(tags: list[str]) -> Gtk.Widget:
    """A wrapping row of rounded feature pills."""
    _ensure_tag_css()
    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(99)
    flow.set_column_spacing(4)
    flow.set_row_spacing(4)
    flow.set_halign(Gtk.Align.START)
    for tag in tags:
        color = _FEATURE_COLORS.get(tag, "#7f8c8d")
        lbl = Gtk.Label(label=tag)
        lbl.add_css_class("pack-tag")
        lbl.add_css_class(f"pack-tag-{color.lstrip('#')}")
        child = Gtk.FlowBoxChild()
        child.set_child(lbl)
        child.set_focusable(False)
        flow.append(child)
    return flow


def _build_pack_row(pack_dir: Path, display_name: str, description: str,
                    tags: list[str], btn_box: Gtk.Widget) -> Gtk.Widget:
    """A custom installed-pack row: icon, title + description + feature pills,
    and the action buttons."""
    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    outer.set_margin_start(8); outer.set_margin_end(8)
    outer.set_margin_top(8);  outer.set_margin_bottom(8)

    outer.set_valign(Gtk.Align.CENTER)

    icon = _pack_icon_prefix(pack_dir, size=48)
    icon.set_valign(Gtk.Align.START)
    outer.append(icon)

    info_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    info_col.set_hexpand(True)
    info_col.set_valign(Gtk.Align.START)

    title = Gtk.Label(xalign=0)
    title.set_markup(f"<b>{GLib.markup_escape_text(display_name)}</b>")
    info_col.append(title)

    if description:
        desc = Gtk.Label(xalign=0, wrap=True)
        desc.set_text(description)
        desc.add_css_class("dim-label")
        desc.add_css_class("caption")
        desc.set_max_width_chars(52)
        # Cap to 2 lines with an ellipsis so rows stay an even height.
        desc.set_lines(2)
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        info_col.append(desc)

    if tags:
        info_col.append(_pills_box(tags))

    outer.append(info_col)

    btn_box.set_valign(Gtk.Align.CENTER)
    outer.append(btn_box)
    return outer


def pack_detail_groups(pack: Pack) -> list[Adw.PreferencesGroup]:
    """The read-only pack detail groups (status, content, information, Discord)
    shown on the dashboard's Pack view."""
    groups: list[Adw.PreferencesGroup] = []

    status = Adw.PreferencesGroup(title="Pack Status")
    status.add(_status_row("Pack Loaded", pack.paths.root.exists()))
    status.add(_status_row("Info File", pack.paths.info.is_file()))
    status.add(_status_row("Wallpaper", pack.paths.wallpaper.is_file()))
    status.add(_status_row(
        "Custom Startup", bool(pack.paths.splash),
        "For older packs, put the file in /resource/ named \"loading_splash.png\"."))
    status.add(_status_row("Custom Discord Status", pack.paths.discord.is_file()))
    status.add(_status_row(
        "Custom Icon", pack.paths.icon.is_file(),
        "Put the file in /resource/ named \"icon.ico\"."))
    status.add(_status_row(
        "Corruption", pack.paths.corruption.is_file(),
        "An Edgeware++ feature that changes content over time."))
    groups.append(status)

    content = Adw.PreferencesGroup(title="Content")
    content.add(_count_row("Images", len(pack.images)))
    content.add(_count_row("Audio Files", len(pack.audio)))
    content.add(_count_row("Videos", len(pack.videos)))
    content.add(_count_row("Web Links", _list_length(pack, "web")))
    content.add(_count_row("Prompts", _list_length(pack, "prompts")))
    content.add(_count_row("Captions", _list_length(pack, "captions")))
    content.add(_count_row("Hypnos", len(pack.hypnos)))
    groups.append(content)

    info = Adw.PreferencesGroup(title="Information", description=INFO_TEXT)
    info.set_sensitive(pack.paths.info.is_file())
    info.add(_value_row("Pack Name", pack.info.name))
    info.add(_value_row("Author Name", pack.info.creator))
    info.add(_value_row("Version", pack.info.version))
    desc_row = Adw.ActionRow(title="Description")
    desc_row.set_subtitle(GLib.markup_escape_text(pack.info.description or ""))
    info.add(desc_row)
    groups.append(info)

    discord = Adw.PreferencesGroup(title="Discord Information", description=DISCORD_TEXT)
    discord.set_sensitive(pack.paths.discord.is_file())
    status_row = Adw.ActionRow(title="Custom Discord Status")
    status_row.set_subtitle(GLib.markup_escape_text(pack.discord.text or ""))
    discord.add(status_row)
    image_row = Adw.ActionRow(title="Discord Status Image")
    image_row.set_subtitle(GLib.markup_escape_text(pack.discord.image or ""))
    image_row.set_tooltip_text(
        "The image is fetched from the Discord application API, which can't be "
        "accessed without permissions, so it can't be previewed here."
    )
    discord.add(image_row)
    groups.append(discord)
    return groups


def _square_pixbuf(path: Path, size: int):
    """Load `path` and centre-crop it to an exact size×size square pixbuf, so
    every pack icon renders identically regardless of source aspect ratio."""
    pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
    w, h = pb.get_width(), pb.get_height()
    if w <= 0 or h <= 0:
        return None
    scale = size / min(w, h)
    sw, sh = max(size, round(w * scale)), max(size, round(h * scale))
    pb = pb.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
    x, y = (sw - size) // 2, (sh - size) // 2
    return GdkPixbuf.Pixbuf.new_subpixbuf(pb, x, y, size, size)


def _pack_icon_prefix(pack_dir: Path, size: int = 32) -> Gtk.Widget:
    """A pack icon centre-cropped to an exact size×size square in a card frame."""
    image = Gtk.Image()
    image.set_pixel_size(size)

    icon_path = pack_dir / "icon.ico"
    pb = None
    if icon_path.is_file():
        try:
            pb = _square_pixbuf(icon_path, size)
        except Exception:
            pb = None
    if pb is None:
        from paths import CustomAssets
        fallback = CustomAssets.icon()
        if fallback.is_file():
            try:
                pb = _square_pixbuf(fallback, size)
            except Exception:
                pb = None
    if pb is not None:
        image.set_from_pixbuf(pb)

    frame = Gtk.Frame()
    frame.add_css_class("card")
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    frame.set_halign(Gtk.Align.CENTER)
    frame.set_valign(Gtk.Align.CENTER)
    frame.set_size_request(size, size)
    frame.set_child(image)
    return frame


def _read_pack_info(pack_dir: Path) -> dict:
    """Cheaply read name/description from info.json without loading the full Pack."""
    for candidate in ("info.json", "resource/info.json"):
        p = pack_dir / candidate
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _status_row(title: str, ok: bool, tooltip: str | None = None) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    if tooltip:
        row.set_tooltip_text(tooltip)
    lbl = Gtk.Label(label="✓" if ok else "✗")
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.add_css_class("status-ok" if ok else "status-fail")
    row.add_suffix(lbl)
    return row


def _count_row(title: str, number: int) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    lbl = Gtk.Label(label=str(number))
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.add_css_class("stats-number")
    row.add_suffix(lbl)
    return row


def _value_row(title: str, value: str) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title)
    row.set_subtitle(GLib.markup_escape_text(value or ""))
    return row


def _list_length(pack: Pack, attr: str) -> int:
    return len(getattr(pack.index.default, attr)) + sum(
        [len(getattr(mood, attr)) for mood in pack.index.moods]
    )
