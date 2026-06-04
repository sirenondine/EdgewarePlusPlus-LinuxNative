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
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

"""Pack editor content controller.

PackEditorContent owns the PackEditor backend and debounced autosave state.
It builds its UI groups into any Adw.PreferencesPage the caller provides, so
it can be embedded in a NavigationPage (slide-in) without needing its own window.
"""

from collections.abc import Callable
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from config.gtk_window.toast import toast
from config.gtk_window.widgets import make_string_list_group
from pack.edit import DEFAULT_TEXT_LISTS, PackEditor

_LIST_META: dict[str, tuple[str, str]] = {
    "captions":      ("Captions",      "Text shown on image popups."),
    "denial":        ("Denial",        "Shown when a popup is denied."),
    "subliminals":   ("Subliminals",   "Full-screen text that flashes briefly."),
    "notifications": ("Notifications", "Text for desktop-notification popups."),
    "prompts":       ("Prompts",       "Words the user must type to close a prompt popup."),
}
_SAVE_DEBOUNCE_MS = 400


class PackEditorContent:
    """Autosave controller for the pack editor.

    Call build_into(page) to populate an Adw.PreferencesPage with the editor
    UI. Then call flush() before navigating away so no pending save is lost.
    saved_any is True if at least one successful write occurred this session.
    """

    def __init__(self, pack_dir: Path) -> None:
        self.editor = PackEditor(pack_dir)
        self.saved_any = False
        self._dirty_info = False
        self._dirty_index = False
        self._save_source: int | None = None
        self._push_page = None
        self._pop_page = None

    def build_into(self, page: Adw.PreferencesPage,
                   push_page=None, pop_page=None) -> None:
        """Populate `page` with the editor groups.

        `push_page` / `pop_page` are callables the caller provides to navigate
        the surrounding NavigationView (push a new page, or go back). If None,
        mood rows are non-interactive.
        """
        self._push_page = push_page
        self._pop_page = pop_page
        self._build_info_group(page)
        if self.editor.has_index:
            self._build_text_groups(page)
            self._build_strings_group(page)
            self._build_moods_group(page)
            self._build_media_row(page)
        else:
            self._build_legacy_notice(page)
        self._build_assets_group(page)
        self._build_discord_group(page)
        self._build_companion_row(page)

    # --- info.json --------------------------------------------------------
    def _build_info_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Pack Information",
            description="Shown in the pack list and the dashboard.",
        )
        page.add(group)
        for field, title in (("name", "Name"), ("creator", "Creator"),
                             ("version", "Version"), ("description", "Description")):
            row = Adw.EntryRow(title=title)
            row.set_text(self.editor.get_info(field))
            row.connect("changed", self._make_info_handler(field))
            group.add(row)

    def _make_info_handler(self, field: str) -> Callable:
        def handler(row: Adw.EntryRow) -> None:
            self.editor.set_info(field, row.get_text())
            self._dirty_info = True
            self._schedule_save()
        return handler

    # --- index.json default text ------------------------------------------
    def _build_text_groups(self, page: Adw.PreferencesPage) -> None:
        pack_name = self.editor.get_info("name") or self.editor.pack_dir.name
        for key in DEFAULT_TEXT_LISTS:
            title, description = _LIST_META[key]
            appender: list = []
            gen_btn = self._make_gen_btn(title, pack_name, appender)
            page.add(make_string_list_group(
                title, description,
                initial=self.editor.get_list(key),
                on_change=self._make_list_handler(key),
                add_prompt=f"{title} entry",
                header_extra=[gen_btn],
                appender_out=appender,
            ))

    def _make_list_handler(self, key: str) -> Callable:
        def handler(items: list[str]) -> None:
            self.editor.set_list(key, items)
            self._dirty_index = True
            self._schedule_save()
        return handler

    def _build_strings_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Default Popup Strings",
            description="Button labels and prompt settings for the default mood.",
        )
        page.add(group)
        for key, title in (("popupClose",     "Popup Close Button"),
                           ("promptCommand",  "Prompt Command Text"),
                           ("promptSubmit",   "Prompt Submit Button")):
            row = Adw.EntryRow(title=title)
            row.set_text(self.editor.get_string(key))
            row.connect("changed", self._make_string_handler(key))
            group.add(row)

        for key, title in (("promptMinLength", "Prompt Min Length"),
                           ("promptMaxLength", "Prompt Max Length")):
            adj = Gtk.Adjustment(
                value=self.editor.get_int(key, 1), lower=1, upper=999, step_increment=1)
            row = Adw.SpinRow(title=title, adjustment=adj)
            row.connect("notify::value", self._make_spin_handler(key))
            group.add(row)

    def _make_string_handler(self, key: str) -> Callable:
        def handler(row: Adw.EntryRow) -> None:
            self.editor.set_string(key, row.get_text())
            self._dirty_index = True
            self._schedule_save()
        return handler

    def _make_spin_handler(self, key: str) -> Callable:
        def handler(row: Adw.SpinRow, _param) -> None:
            self.editor.set_int(key, int(row.get_value()))
            self._dirty_index = True
            self._schedule_save()
        return handler

    def _build_moods_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Moods",
            description="Named content groups. Click a mood to edit its text lists.",
        )
        page.add(group)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add mood")
        from config.gtk_window.toast import name_popover
        add_btn.connect("clicked", lambda b: name_popover(
            b, "New mood name", self._on_add_mood_commit(group)))
        group.set_header_suffix(add_btn)

        for name in self.editor.mood_names():
            self._append_mood_row(group, name)

    def _append_mood_row(self, group: Adw.PreferencesGroup, name: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=name)
        row.set_subtitle(f"{len(self.editor.get_mood_list(name, 'captions'))} captions  "
                         f"{len(self.editor.get_mood_list(name, 'media'))} media")
        row.set_activatable(self._push_page is not None)

        if self._push_page is not None:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda _r, n=name: self._push_mood_page(n))

        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.set_tooltip_text("Delete mood")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _b, r=row, n=name: self._on_delete_mood(r, n))
        row.add_suffix(del_btn)

        group.add(row)
        return row

    def _on_add_mood_commit(self, group: Adw.PreferencesGroup):
        def commit(name: str) -> None:
            err = self.editor.add_mood(name)
            if err:
                toast(err)
                return
            self._append_mood_row(group, name.strip())
            self._dirty_index = True
            self._schedule_save()
        return commit

    def _on_delete_mood(self, row: Adw.ActionRow, name: str) -> None:
        from gtk_dialog import ask_yes_no
        media_count = len(self.editor.get_mood_list(name, "media"))
        detail = f"{media_count} media file{'s' if media_count != 1 else ''} will become unassigned." if media_count else ""
        if not ask_yes_no(
            f"Delete mood \"{name}\"?",
            detail or f"The mood \"{name}\" will be permanently removed.",
            heading="Delete mood?",
        ):
            return
        self.editor.remove_mood(name)
        parent = row.get_parent()
        if parent:
            while parent and not isinstance(parent, Adw.PreferencesGroup):
                parent = parent.get_parent()
            if isinstance(parent, Adw.PreferencesGroup):
                parent.remove(row)
        self._dirty_index = True
        self._schedule_save()

    def _push_mood_page(self, mood_name: str) -> None:
        if not self._push_page:
            return
        pref = Adw.PreferencesPage()
        pref.set_vexpand(True)

        # Mood name editor (rename).
        rename_group = Adw.PreferencesGroup(title="Mood Name")
        name_row = Adw.EntryRow(title="Name")
        name_row.set_text(mood_name)
        rename_group.add(name_row)
        pref.add(rename_group)

        # Per-mood text lists.
        pack_name = self.editor.get_info("name") or self.editor.pack_dir.name
        context = f"{pack_name} / {mood_name} mood"
        for key in DEFAULT_TEXT_LISTS:
            title, description = _LIST_META[key]
            appender: list = []
            gen_btn = self._make_gen_btn(title, context, appender)
            pref.add(make_string_list_group(
                title, description,
                initial=self.editor.get_mood_list(mood_name, key),
                on_change=self._make_mood_list_handler(mood_name, key),
                add_prompt=f"{title} entry",
                header_extra=[gen_btn],
                appender_out=appender,
            ))

        # Per-mood strings.
        strings_group = Adw.PreferencesGroup(
            title="Mood Popup Strings",
            description="Override the popup close label and max clicks for this mood.",
        )
        for key, title in (("popupClose", "Popup Close Button"),):
            r = Adw.EntryRow(title=title)
            r.set_text(self.editor.get_mood_string(mood_name, key))
            r.connect("changed", self._make_mood_string_handler(mood_name, key))
            strings_group.add(r)

        adj = Gtk.Adjustment(
            value=self.editor.get_mood_int(mood_name, "maxClicks", 1),
            lower=1, upper=999, step_increment=1)
        clicks_row = Adw.SpinRow(title="Max Clicks", adjustment=adj)
        clicks_row.connect("notify::value",
            lambda r, _p: (self.editor.set_mood_int(mood_name, "maxClicks", int(r.get_value())),
                           self._mark_index_dirty()))
        strings_group.add(clicks_row)
        pref.add(strings_group)

        # Wire rename on change (after mood_name is captured).
        name_row.connect("changed", self._make_mood_rename_handler(mood_name))

        # Back button + ToolbarView wrapper.
        back_btn = Gtk.Button()
        back_btn.set_child(Adw.ButtonContent(
            icon_name="go-previous-symbolic", label="Edit Pack"))
        back_btn.set_halign(Gtk.Align.START)
        back_btn.set_margin_start(6)
        back_btn.connect("clicked", lambda _: self._pop_page() if self._pop_page else None)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top_bar.append(back_btn)
        tv = Adw.ToolbarView()
        tv.add_top_bar(top_bar)
        tv.set_content(pref)

        nav_page = Adw.NavigationPage.new(tv, f"Mood: {mood_name}")
        self._push_page(nav_page)

    def _mark_index_dirty(self) -> None:
        self._dirty_index = True
        self._schedule_save()

    def _make_mood_list_handler(self, mood_name: str, key: str) -> Callable:
        def handler(items: list[str]) -> None:
            self.editor.set_mood_list(mood_name, key, items)
            self._mark_index_dirty()
        return handler

    def _make_mood_string_handler(self, mood_name: str, key: str) -> Callable:
        def handler(row: Adw.EntryRow) -> None:
            self.editor.set_mood_string(mood_name, key, row.get_text())
            self._mark_index_dirty()
        return handler

    def _make_mood_rename_handler(self, original_name: str) -> Callable:
        # Rename is debounced; we update in-memory immediately but only write on save.
        _current = [original_name]
        def handler(row: Adw.EntryRow) -> None:
            new = row.get_text().strip()
            if not new or new == _current[0]:
                return
            err = self.editor.rename_mood(_current[0], new)
            if err:
                toast(err)
                return
            _current[0] = new
            self._mark_index_dirty()
        return handler

    def _build_media_row(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(title="Media")
        row = Adw.ActionRow(
            title="Assign Media to Moods",
            subtitle="Set which mood each image, video, or audio file belongs to.",
        )
        row.set_activatable(self._push_page is not None)
        if self._push_page is not None:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda _: self._push_media_page())
        page.add(group)
        group.add(row)

    def _push_media_page(self) -> None:
        if not self._push_page:
            return
        from config.gtk_window.media_grid import build_media_page
        nav_page = build_media_page(
            self.editor.pack_dir,
            self.editor,
            on_change=self._mark_index_dirty,
            pop_fn=self._pop_page,
        )
        self._push_page(nav_page)

    # --- AI generation ----------------------------------------------------

    def _make_gen_btn(self, list_type: str, context: str, appender: list) -> Gtk.Button:
        btn = Gtk.Button(icon_name="starred-symbolic")
        btn.set_tooltip_text(f"Generate {list_type} with AI")
        btn.connect("clicked", lambda b: _open_generate_dialog(
            b, list_type, context, appender))
        return btn

    # --- Phase 3: Assets --------------------------------------------------

    def _build_assets_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Assets",
            description="Pack visuals. Changes apply on next pack load.",
        )
        page.add(group)
        for key, title, subtitle in (
            ("icon",     "Pack Icon",       "icon.ico — shown in the pack list"),
            ("wallpaper","Wallpaper",        "wallpaper.png — desktop wallpaper on launch"),
            ("splash",   "Loading Splash",  "loading_splash.* — shown on startup"),
        ):
            group.add(self._make_asset_row(key, title, subtitle))

    def _make_asset_row(self, key: str, title: str, subtitle: str) -> Adw.ActionRow:
        from gi.repository import GdkPixbuf, Gdk

        existing = self.editor.get_asset_path(key)
        row = Adw.ActionRow(title=title, subtitle=existing.name if existing else subtitle)

        # Thumbnail prefix
        preview = Gtk.Picture()
        preview.set_size_request(40, 40)
        preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        preview.set_can_shrink(True)
        if existing:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(existing), 40, 40, True)
                preview.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            except Exception:
                pass
        row.add_prefix(preview)

        # Clear button
        clear_btn = Gtk.Button(icon_name="user-trash-symbolic")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.set_sensitive(existing is not None)
        clear_btn.add_css_class("destructive-action")

        # Choose button
        choose_btn = Gtk.Button()
        choose_btn.set_child(Adw.ButtonContent(
            label="Choose…", icon_name="document-open-symbolic"))
        choose_btn.set_valign(Gtk.Align.CENTER)

        def on_chosen(fd, result, _k=key, _row=row, _preview=preview,
                      _clear=clear_btn) -> None:
            try:
                file = fd.open_finish(result)
            except Exception:
                return
            if not file:
                return
            src = Path(file.get_path())
            err = self.editor.set_asset(_k, src)
            if err:
                toast(f"Could not set asset: {err}")
                return
            new_path = self.editor.get_asset_path(_k)
            _row.set_subtitle(new_path.name if new_path else src.name)
            if new_path:
                try:
                    from gi.repository import GdkPixbuf, Gdk
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(new_path), 40, 40, True)
                    _preview.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
                except Exception:
                    pass
            _clear.set_sensitive(True)

        def on_choose(_b, _k=key) -> None:
            dlg = Gtk.FileDialog()
            dlg.set_title(f"Choose {title}")
            filt = Gtk.FileFilter()
            filt.set_name("Images")
            for mime in ("image/png","image/jpeg","image/gif","image/x-icon","image/bmp","image/webp"):
                filt.add_mime_type(mime)
            dlg.set_default_filter(filt)
            dlg.open(choose_btn.get_root(), None, on_chosen)

        def on_clear(_b, _k=key, _row=row, _preview=preview) -> None:
            self.editor.clear_asset(_k)
            _row.set_subtitle(subtitle)
            _preview.set_paintable(None)
            clear_btn.set_sensitive(False)

        choose_btn.connect("clicked", on_choose)
        clear_btn.connect("clicked", on_clear)
        row.add_suffix(choose_btn)
        row.add_suffix(clear_btn)
        return row

    # --- Phase 3: Discord -------------------------------------------------

    def _build_discord_group(self, page: Adw.PreferencesPage) -> None:
        from pack.edit import DISCORD_IMAGE_IDS
        text, image_id = self.editor.get_discord()
        discord_data = {"text": text, "image": image_id}

        group = Adw.PreferencesGroup(
            title="Discord Status",
            description="Shown in Discord when \"Show on Discord\" is enabled.",
        )
        page.add(group)

        text_row = Adw.EntryRow(title="Status Text")
        text_row.set_text(text)
        group.add(text_row)

        image_options = ["(none)"] + DISCORD_IMAGE_IDS
        image_model = Gtk.StringList.new(image_options)
        image_row = Adw.ComboRow(title="Status Image")
        image_row.set_model(image_model)
        cur_idx = image_options.index(image_id) if image_id in image_options else 0
        image_row.set_selected(cur_idx)
        group.add(image_row)

        def save_discord(*_) -> None:
            t = text_row.get_text()
            idx = image_row.get_selected()
            img = "" if idx == 0 else image_options[idx]
            err = self.editor.save_discord(t, img)
            if err:
                toast(f"Could not save Discord status: {err}")

        text_row.connect("changed", save_discord)
        image_row.connect("notify::selected", save_discord)

    # --- Phase 3: Companion -----------------------------------------------

    def _build_companion_row(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(title="AI Companion")
        row = Adw.ActionRow(
            title="Companion Persona",
            subtitle="Name, avatar, system prompt, greetings, and idle lines.",
        )
        row.set_activatable(self._push_page is not None)
        if self._push_page is not None:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda _: self._push_companion_page())
        page.add(group)
        group.add(row)

    def _push_companion_page(self) -> None:
        if not self._push_page:
            return
        data = self.editor.get_companion()
        pref = Adw.PreferencesPage()
        pref.set_vexpand(True)

        # Basic fields
        basic_group = Adw.PreferencesGroup(title="Identity")
        pref.add(basic_group)
        for field, title in (("name", "Name"), ("avatar", "Avatar filename"),
                             ("spritesheet", "Spritesheet filename")):
            r = Adw.EntryRow(title=title)
            r.set_text(str(data.get(field, "") or ""))
            r.connect("changed", self._make_companion_field_handler(data, field))
            basic_group.add(r)

        # System prompt (multiline via TextView)
        prompt_group = Adw.PreferencesGroup(
            title="System Prompt",
            description="Instructions sent to the LLM defining the companion's personality.",
        )
        pref.add(prompt_group)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_top_margin(8); tv.set_bottom_margin(8)
        tv.set_left_margin(8); tv.set_right_margin(8)
        buf = tv.get_buffer()
        buf.set_text(str(data.get("system_prompt", "") or ""))
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(100)
        sw.set_child(tv)
        frame = Gtk.Frame(); frame.add_css_class("card"); frame.set_child(sw)
        prompt_group.add(frame)
        buf.connect("changed", self._make_companion_text_handler(data, "system_prompt", buf))

        # Text lists
        for key, title, desc in (
            ("greetings",  "Greetings",  "Said when companion first appears."),
            ("idle_lines", "Idle Lines", "Random things said when idle."),
        ):
            pref.add(make_string_list_group(
                title, desc,
                initial=list(data.get(key, []) or []),
                on_change=self._make_companion_list_handler(data, key),
                add_prompt=f"{title} entry",
            ))

        back_btn = Gtk.Button()
        back_btn.set_child(Adw.ButtonContent(
            icon_name="go-previous-symbolic", label="Edit Pack"))
        back_btn.set_halign(Gtk.Align.START)
        back_btn.set_margin_start(6)
        back_btn.connect("clicked", lambda _: self._pop_page() if self._pop_page else None)
        top_bar = Gtk.Box(); top_bar.append(back_btn)
        tv_wrapper = Adw.ToolbarView()
        tv_wrapper.add_top_bar(top_bar); tv_wrapper.set_content(pref)

        self._push_page(Adw.NavigationPage.new(tv_wrapper, "Companion Persona"))

    def _make_companion_field_handler(self, data: dict, field: str):
        def handler(row: Adw.EntryRow) -> None:
            data[field] = row.get_text() or None
            self._save_companion(data)
        return handler

    def _make_companion_text_handler(self, data: dict, field: str, buf: Gtk.TextBuffer):
        def handler(_buf) -> None:
            data[field] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self._save_companion(data)
        return handler

    def _make_companion_list_handler(self, data: dict, key: str):
        def handler(items: list[str]) -> None:
            data[key] = items
            self._save_companion(data)
        return handler

    def _save_companion(self, data: dict) -> None:
        err = self.editor.save_companion(data)
        if err:
            toast(f"Could not save companion: {err}")

    def _build_legacy_notice(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Popup Text",
            description="This pack uses the legacy format (captions.json / media.json / "
                        "prompt.json / web.json). Migrate to index.json to enable text editing "
                        "and media assignment. Legacy files are kept — migration is non-destructive.",
        )
        page.add(group)

        has_legacy = self.editor.has_legacy

        migrate_row = Adw.ActionRow(
            title="Migrate to index.json" if has_legacy else "No migratable legacy files found",
            subtitle="Combines legacy files into a single modern index.json." if has_legacy
                     else "Pack has neither index.json nor legacy caption/media files.",
        )

        if has_legacy:
            migrate_btn = Gtk.Button()
            migrate_btn.set_child(Adw.ButtonContent(
                label="Migrate…", icon_name="emblem-synchronizing-symbolic"))
            migrate_btn.set_valign(Gtk.Align.CENTER)
            migrate_btn.connect("clicked", self._on_migrate)
            migrate_row.add_suffix(migrate_btn)
            migrate_row.set_activatable_widget(migrate_btn)
        else:
            migrate_row.set_sensitive(False)

        group.add(migrate_row)

    def _on_migrate(self, _btn) -> None:
        from gtk_dialog import ask_yes_no
        from config.gtk_window.utils import refresh

        # Show what will be migrated
        pack_dir = self.editor.pack_dir
        legacy = [f for f in ("captions.json","media.json","prompt.json","web.json")
                  if (pack_dir / f).is_file()]
        files_str = "\n".join(f"  • {f}" for f in legacy)
        if not ask_yes_no(
            "Migrate to index.json?",
            f"The following files will be read and combined into index.json:\n{files_str}\n\n"
            "Legacy files are kept — nothing will be deleted.",
            heading="Migrate pack format?",
        ):
            return

        err = self.editor.migrate_legacy_to_index()
        if err:
            toast(f"Migration failed: {err}")
            return

        toast("Migration complete. Reloading editor…")
        refresh()

    # --- debounced autosave -----------------------------------------------
    def _schedule_save(self) -> None:
        if self._save_source is not None:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(_SAVE_DEBOUNCE_MS, self._do_save)

    def _do_save(self) -> bool:
        self._save_source = None
        if self._dirty_info:
            self._dirty_info = False
            err = self.editor.save_info()
            if err:
                toast(f"Could not save pack info: {err}")
            else:
                self.saved_any = True
        if self._dirty_index:
            self._dirty_index = False
            err = self.editor.save_index()
            if err:
                toast(f"Could not save pack text: {err}")
            else:
                self.saved_any = True
        return False  # one-shot GLib source

    def flush(self) -> None:
        """Flush any pending debounced save immediately."""
        if self._save_source is not None:
            GLib.source_remove(self._save_source)
            self._save_source = None
        self._do_save()


# ---------------------------------------------------------------------------
# AI generation dialog (module-level so it works without a PackEditorContent)
# ---------------------------------------------------------------------------

def _make_backend_from_config():
    """Build an LLM backend from the current config.json. Returns None if the
    companion is disabled or no network backend is configured."""
    try:
        from config import load_config
        from features.companion.llm import make_backend
        c = load_config()
        if not c.get("companionEnabled"):
            return None
        backend = c.get("companionBackend", "scripted")
        if backend == "scripted":
            return None  # scripted can't generate useful content
        return make_backend(
            backend,
            base_url=c.get("companionBaseUrl") or None,
            model=c.get("companionModel") or None,
            api_key=c.get("companionApiKey") or None,
        )
    except Exception:
        return None


def _open_generate_dialog(
    anchor: Gtk.Widget,
    list_type: str,
    context: str,
    appender: list,
) -> None:
    """Open a modal generation window. `appender` is a one-element list
    containing a `bulk_append(items)` fn from make_string_list_group."""
    from threading import Thread

    win = Gtk.Window(title=f"Generate {list_type}")
    win.set_default_size(500, 540)
    win.set_modal(True)
    root = anchor.get_root()
    if root:
        win.set_transient_for(root)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(16); box.set_margin_end(16)
    box.set_margin_top(16);  box.set_margin_bottom(16)
    win.set_child(box)

    ctx_lbl = Gtk.Label(label=f"Context: {context}")
    ctx_lbl.add_css_class("dim-label")
    ctx_lbl.set_halign(Gtk.Align.START)
    box.append(ctx_lbl)

    theme_row = Adw.EntryRow(title="Theme / extra instructions (optional)")
    box.append(theme_row)

    count_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    count_box.set_halign(Gtk.Align.START)
    count_box.append(Gtk.Label(label="Generate "))
    count_adj = Gtk.Adjustment(value=10, lower=1, upper=50, step_increment=1)
    count_spin = Gtk.SpinButton(adjustment=count_adj, digits=0)
    count_box.append(count_spin)
    count_box.append(Gtk.Label(label=f" {list_type.lower()} entries"))
    box.append(count_box)

    gen_btn = Gtk.Button(label="Generate")
    gen_btn.add_css_class("suggested-action")
    box.append(gen_btn)

    # Live preview
    tv = Gtk.TextView()
    tv.set_editable(False)
    tv.set_wrap_mode(Gtk.WrapMode.WORD)
    tv.set_top_margin(8); tv.set_bottom_margin(8)
    tv.set_left_margin(8); tv.set_right_margin(8)
    buf = tv.get_buffer()
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_vexpand(True)
    sw.set_min_content_height(220)
    sw.set_child(tv)
    frame = Gtk.Frame(); frame.add_css_class("card"); frame.set_child(sw)
    box.append(frame)

    # Bottom bar
    btn_row = Gtk.Box(spacing=8)
    btn_row.set_halign(Gtk.Align.END)
    cancel_btn = Gtk.Button(label="Cancel")
    cancel_btn.connect("clicked", lambda _: win.close())
    add_btn = Gtk.Button()
    add_btn.set_sensitive(False)
    btn_row.append(cancel_btn)
    btn_row.append(add_btn)
    box.append(btn_row)

    _generated: list[list[str]] = [[]]  # mutable container

    def do_generate(_b) -> None:
        theme = theme_row.get_text().strip()
        count = int(count_adj.get_value())
        buf.set_text("")
        gen_btn.set_sensitive(False)
        add_btn.set_sensitive(False)
        _generated[0] = []

        backend = _make_backend_from_config()
        if backend is None:
            buf.set_text(
                "No LLM backend available.\n\n"
                "Enable the AI Companion and configure Ollama or an OpenAI-compatible "
                "endpoint in Settings → Companion."
            )
            gen_btn.set_sensitive(True)
            return

        system = (
            f"You are a creative writer for an adult popup software pack called \"{context}\". "
            f"Generate exactly {count} short {list_type.lower()} entries, one per line. "
            f"No numbering, no bullet points, no preamble, no empty lines. "
            f"Just the {count} entries, each on its own line."
        )
        user_msg = (
            f"Theme: {theme}. " if theme else ""
        ) + f"Generate {count} {list_type.lower()} entries now."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        def on_token(tok: str) -> None:
            GLib.idle_add(_buf_append, buf, tok)

        def on_done(full: str) -> None:
            items = [ln.strip() for ln in full.splitlines() if ln.strip()][:count]
            _generated[0] = items
            label = f"Add {len(items)} to list"
            GLib.idle_add(add_btn.set_child, Adw.ButtonContent(
                label=label, icon_name="list-add-symbolic"))
            GLib.idle_add(add_btn.add_css_class, "suggested-action")
            GLib.idle_add(add_btn.set_sensitive, bool(items))
            GLib.idle_add(gen_btn.set_sensitive, True)

        def on_error(exc: Exception) -> None:
            GLib.idle_add(_buf_append, buf, f"\n\nError: {exc}")
            GLib.idle_add(gen_btn.set_sensitive, True)

        Thread(
            target=backend.stream,
            args=(messages, on_token, on_done, on_error),
            daemon=True,
        ).start()

    def do_add(_b) -> None:
        items = _generated[0]
        if items and appender:
            appender[0](items)
        win.close()

    gen_btn.connect("clicked", do_generate)
    add_btn.connect("clicked", do_add)
    win.present()


def _buf_append(buf: Gtk.TextBuffer, text: str) -> bool:
    buf.insert(buf.get_end_iter(), text)
    return False
