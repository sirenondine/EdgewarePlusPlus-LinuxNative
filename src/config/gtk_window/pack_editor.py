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

# Richer per-type guidance for the LLM, keyed by display title. Tells the model
# what each list actually is (the bare word "denial"/"subliminals" isn't enough).
_GEN_TYPE_GUIDANCE: dict[str, str] = {
    "Captions": "captions displayed over image popups — short teasing or encouraging "
                "lines that comment on the image or talk to the viewer",
    "Denial": "denial messages shown when a popup is blurred and withheld — teasingly "
              "refuse and deny the viewer what they want to see",
    "Subliminals": "subliminal phrases that flash full-screen for a split second — very "
                   "short, punchy, hypnotic commands or affirmations (a few words each)",
    "Notifications": "desktop notification messages — short lines like a system "
                     "notification popup would display",
    "Prompts": "words or very short phrases the viewer must type to dismiss a prompt "
               "popup — keep each entry to one to a few words, easy to type",
    "Greetings": "greeting lines the AI companion says when it first appears — short, "
                 "in-character opening lines spoken directly to the user",
    "Idle Lines": "idle remarks the AI companion says at random while nothing is "
                  "happening — short, in-character chatter spoken to the user",
}
_SAVE_DEBOUNCE_MS = 400

# Friendly display labels for Discord rich-presence asset ids.
_DISCORD_LABELS = {
    "furcock_img": "Furry", "blacked_img": "Blacked", "censored_img": "Censored",
    "goon_img": "Goon", "goon2_img": "Goon (alt)", "hypno_img": "Hypno",
    "futa_img": "Futa", "healslut_img": "Healslut", "gross_img": "Gross",
}


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
        self._on_migrated = None
        self._page = None
        self._moods_group: "Adw.PreferencesGroup | None" = None
        self._mood_rows: list = []

    def build_into(self, page: Adw.PreferencesPage,
                   push_page=None, pop_page=None, on_migrated=None) -> None:
        """Populate `page` with the editor groups.

        `push_page` / `pop_page` are callables the caller provides to navigate
        the surrounding NavigationView (push a new page, or go back). If None,
        mood rows are non-interactive. `on_migrated` is called after a legacy
        migration so the host can rebuild this page in place (no window reload).
        """
        self._push_page = push_page
        self._pop_page = pop_page
        self._on_migrated = on_migrated
        self._page = page
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
        self._build_config_save_group(page)
        if self.editor.has_index:
            self._build_corruption_row(page)

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
        self._moods_group = group

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add mood")
        from config.gtk_window.toast import name_popover
        add_btn.connect("clicked", lambda b: name_popover(
            b, "New mood name", self._on_add_mood_commit()))
        group.set_header_suffix(add_btn)

        self._rebuild_moods()

    def _rebuild_moods(self) -> None:
        for row in self._mood_rows:
            self._moods_group.remove(row)
        self._mood_rows = []
        for name in self.editor.mood_names():
            self._append_mood_row(self._moods_group, name)

    def _append_mood_row(self, group: Adw.PreferencesGroup, name: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=name)
        # Canonical mood name lives on the row, kept in sync on rename, so the
        # activate/delete handlers never use a stale captured name.
        row._mood_name = name  # type: ignore[attr-defined]
        row.set_subtitle(f"{len(self.editor.get_mood_list(name, 'captions'))} captions  "
                         f"{len(self.editor.get_mood_list(name, 'media'))} media")
        row.set_activatable(self._push_page is not None)

        # Suffix order: last add_suffix = leftmost. Target: [↑↓] [🗑️] [→]
        # So add: nav arrow first, del second, reorder box third (last = leftmost).
        if self._push_page is not None:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda r: self._push_mood_page(r))

        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.set_tooltip_text("Delete mood")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _b, r=row: self._on_delete_mood(r))
        row.add_suffix(del_btn)

        names = self.editor.mood_names()
        reorder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        reorder_box.add_css_class("linked")
        reorder_box.set_valign(Gtk.Align.CENTER)

        up_btn = Gtk.Button(icon_name="go-up-symbolic")
        up_btn.set_tooltip_text("Move mood up")
        up_btn.set_sensitive(name != names[0] if names else False)
        up_btn.connect("clicked", lambda _b, n=name: self._on_move_mood(n, -1))
        reorder_box.append(up_btn)

        down_btn = Gtk.Button(icon_name="go-down-symbolic")
        down_btn.set_tooltip_text("Move mood down")
        down_btn.set_sensitive(name != names[-1] if names else False)
        down_btn.connect("clicked", lambda _b, n=name: self._on_move_mood(n, +1))
        reorder_box.append(down_btn)

        row.add_suffix(reorder_box)

        group.add(row)
        self._mood_rows.append(row)
        return row

    def _on_add_mood_commit(self):
        def commit(name: str) -> None:
            err = self.editor.add_mood(name)
            if err:
                toast(err)
                return
            self._rebuild_moods()
            self._dirty_index = True
            self._schedule_save()
        return commit

    def _on_move_mood(self, name: str, direction: int) -> None:
        self.editor.move_mood(name, direction)
        self._rebuild_moods()
        self._dirty_index = True
        self._schedule_save()

    def _on_delete_mood(self, row: Adw.ActionRow) -> None:
        from gtk_dialog import ask_yes_no
        name = row._mood_name  # type: ignore[attr-defined]
        media_count = len(self.editor.get_mood_list(name, "media"))
        detail = f"{media_count} media file{'s' if media_count != 1 else ''} will become unassigned." if media_count else ""
        if not ask_yes_no(
            f"Delete mood \"{name}\"?",
            detail or f"The mood \"{name}\" will be permanently removed.",
            heading="Delete mood?",
        ):
            return
        self.editor.remove_mood(name)
        self._rebuild_moods()
        self._dirty_index = True
        self._schedule_save()

    def _push_mood_page(self, source_row: Adw.ActionRow) -> None:
        if not self._push_page:
            return
        mood_name = source_row._mood_name  # type: ignore[attr-defined]
        # Live name reference shared by every handler on this page, so a rename
        # mid-session keeps captions/strings/maxClicks edits pointed at the
        # current mood instead of a stale captured name.
        name_ref = [mood_name]

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
                on_change=self._make_mood_list_handler(name_ref, key),
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
            r.connect("changed", self._make_mood_string_handler(name_ref, key))
            strings_group.add(r)

        adj = Gtk.Adjustment(
            value=self.editor.get_mood_int(mood_name, "maxClicks", 1),
            lower=1, upper=999, step_increment=1)
        clicks_row = Adw.SpinRow(title="Max Clicks", adjustment=adj)
        clicks_row.connect("notify::value",
            lambda r, _p: (self.editor.set_mood_int(name_ref[0], "maxClicks", int(r.get_value())),
                           self._mark_index_dirty()))
        strings_group.add(clicks_row)
        pref.add(strings_group)

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

        # Rename: update in-memory mood + the live ref + the page title + the
        # source row in the moods list (title + canonical name).
        name_row.connect("changed", self._make_mood_rename_handler(
            name_ref, nav_page, source_row))

        self._push_page(nav_page)

    def _mark_index_dirty(self) -> None:
        self._dirty_index = True
        self._schedule_save()

    def _make_mood_list_handler(self, name_ref: list, key: str) -> Callable:
        def handler(items: list[str]) -> None:
            self.editor.set_mood_list(name_ref[0], key, items)
            self._mark_index_dirty()
        return handler

    def _make_mood_string_handler(self, name_ref: list, key: str) -> Callable:
        def handler(row: Adw.EntryRow) -> None:
            self.editor.set_mood_string(name_ref[0], key, row.get_text())
            self._mark_index_dirty()
        return handler

    def _make_mood_rename_handler(self, name_ref: list, nav_page: Adw.NavigationPage,
                                  source_row: Adw.ActionRow) -> Callable:
        def handler(row: Adw.EntryRow) -> None:
            new = row.get_text().strip()
            if not new or new == name_ref[0]:
                return
            # Collision with another mood (transient while typing) — skip quietly
            # so we don't spam toasts; the final unique name will apply.
            if new in self.editor.mood_names() and new != name_ref[0]:
                return
            err = self.editor.rename_mood(name_ref[0], new)
            if err:
                return
            name_ref[0] = new
            nav_page.set_title(f"Mood: {new}")
            source_row.set_title(new)
            source_row._mood_name = new  # type: ignore[attr-defined]
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
        type_hint = _GEN_TYPE_GUIDANCE.get(list_type, "")
        pack_desc = self.editor.get_info("description")
        btn.connect("clicked", lambda b: _open_generate_dialog(
            b, list_type, context, appender, type_hint=type_hint, pack_desc=pack_desc))
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

        group = Adw.PreferencesGroup(
            title="Discord Status",
            description="Shown in Discord when \"Show on Discord\" is enabled. The "
                        "status image is one of Edgeware's fixed Discord assets — it "
                        "is hosted by the Discord app and can't be previewed here.",
        )
        page.add(group)

        text_row = Adw.EntryRow(title="Status Text")
        text_row.set_text(text)
        group.add(text_row)

        # Status image row: live thumbnail + label + "Choose" → thumbnail picker
        # of the actual Discord assets (fetched from Discord's CDN).
        self._discord_image = image_id
        image_row = Adw.ActionRow(title="Status Image")
        image_row.set_subtitle(_DISCORD_LABELS.get(image_id, image_id) if image_id else "None")

        thumb = Gtk.Picture()
        thumb.set_size_request(48, 48)
        thumb.set_content_fit(Gtk.ContentFit.CONTAIN)
        thumb.set_can_shrink(True)
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_valign(Gtk.Align.CENTER)
        frame.set_child(thumb)
        image_row.add_prefix(frame)
        self._load_discord_thumb(thumb, image_id)

        choose_btn = Gtk.Button()
        choose_btn.set_child(Adw.ButtonContent(label="Choose…", icon_name="image-x-generic-symbolic"))
        choose_btn.set_valign(Gtk.Align.CENTER)
        choose_btn.connect("clicked", lambda _b, r=image_row, t=thumb, tr=text_row:
                           self._open_discord_picker(r, t, tr))
        image_row.add_suffix(choose_btn)
        group.add(image_row)

        text_row.connect("changed", lambda r: self._save_discord(r.get_text()))

    def _save_discord(self, text: str) -> None:
        err = self.editor.save_discord(text, self._discord_image)
        if err:
            toast(f"Could not save Discord status: {err}")

    def _load_discord_thumb(self, picture: Gtk.Picture, image_id: str) -> None:
        from threading import Thread
        from gi.repository import Gdk, GdkPixbuf
        if not image_id:
            picture.set_paintable(None)
            return

        def work() -> None:
            from config.gtk_window.discord_assets import fetch_assets
            url = fetch_assets().get(image_id)
            if not url:
                return
            try:
                import requests
                data = requests.get(url, timeout=10).content
                loader = GdkPixbuf.PixbufLoader()
                loader.write(data); loader.close()
                pb = loader.get_pixbuf()
                if pb:
                    GLib.idle_add(picture.set_paintable, Gdk.Texture.new_for_pixbuf(pb))
            except Exception:
                pass
        Thread(target=work, daemon=True).start()

    def _open_discord_picker(self, row, thumb, text_row) -> None:
        from threading import Thread
        from config.gtk_window.discord_assets import fetch_assets

        root = self._page.get_root() if self._page else None

        def work() -> None:
            assets = fetch_assets()  # {name: url}
            from pack.edit import DISCORD_IMAGE_IDS
            items = [
                (_DISCORD_LABELS.get(name, name), name, assets[name])
                for name in DISCORD_IMAGE_IDS if name in assets
            ]
            GLib.idle_add(lambda: self._show_discord_picker(root, items, row, thumb))

        Thread(target=work, daemon=True).start()

    def _show_discord_picker(self, root, items, row, thumb) -> bool:
        from config.gtk_window.image_picker import open_remote_image_picker
        if not items:
            toast("Could not load Discord images (offline?).")
            return False

        def on_pick(value: str) -> None:
            self._discord_image = value
            row.set_subtitle(_DISCORD_LABELS.get(value, value) if value else "None")
            self._load_discord_thumb(thumb, value)
            self._save_discord(self._discord_text())

        open_remote_image_picker(root, items, self._discord_image, on_pick,
                                 title="Choose Discord Status Image")
        return False

    def _discord_text(self) -> str:
        # Current text is the persisted one (text_row.changed already saved it).
        return self.editor.get_discord()[0]

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

        pack_name = self.editor.get_info("name") or self.editor.pack_dir.name
        persona_name = str(data.get("name") or "the companion")
        context = f"{pack_name}, companion persona \"{persona_name}\""
        pack_desc = self.editor.get_info("description")

        # Basic fields
        basic_group = Adw.PreferencesGroup(title="Identity")
        pref.add(basic_group)
        name_row = Adw.EntryRow(title="Name")
        name_row.set_text(str(data.get("name", "") or ""))
        name_row.connect("changed", self._make_companion_field_handler(data, "name"))
        basic_group.add(name_row)
        basic_group.add(self._companion_file_row(data, "avatar", "Avatar"))
        basic_group.add(self._companion_file_row(data, "spritesheet", "Spritesheet"))

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

        gen_prompt_btn = Gtk.Button(icon_name="starred-symbolic")
        gen_prompt_btn.set_tooltip_text("Generate a system prompt with AI")
        gen_prompt_btn.connect("clicked", lambda b: _open_prompt_generate_dialog(
            b, context, pack_desc, buf))
        prompt_group.set_header_suffix(gen_prompt_btn)

        # Text lists (with AI generate buttons)
        for key, title, desc in (
            ("greetings",  "Greetings",  "Said when companion first appears."),
            ("idle_lines", "Idle Lines", "Random things said when idle."),
        ):
            appender: list = []
            gen_btn = self._make_gen_btn(title, context, appender)
            pref.add(make_string_list_group(
                title, desc,
                initial=list(data.get(key, []) or []),
                on_change=self._make_companion_list_handler(data, key),
                add_prompt=f"{title} entry",
                header_extra=[gen_btn],
                appender_out=appender,
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

    def _companion_file_row(self, data: dict, field: str, title: str) -> Adw.ActionRow:
        """An image-file picker for a companion asset (avatar/spritesheet). Copies
        the chosen file into the pack root and stores its filename in companion.json."""
        from gi.repository import GdkPixbuf, Gdk

        row = Adw.ActionRow(title=title)
        current = str(data.get(field, "") or "")
        row.set_subtitle(current or "None")

        preview = Gtk.Picture()
        preview.set_size_request(40, 40)
        preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        preview.set_can_shrink(True)
        frame = Gtk.Frame(); frame.add_css_class("card")
        frame.set_valign(Gtk.Align.CENTER); frame.set_child(preview)
        row.add_prefix(frame)

        def load_preview(filename: str) -> None:
            path = self.editor.pack_dir / filename if filename else None
            if path and path.is_file():
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 40, 40, True)
                    preview.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
                    return
                except Exception:
                    pass
            preview.set_paintable(None)
        load_preview(current)

        clear_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_sensitive(bool(current))

        choose_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        choose_btn.set_child(Adw.ButtonContent(label="Choose…", icon_name="document-open-symbolic"))

        def on_chosen(fd, result) -> None:
            try:
                f = fd.open_finish(result)
            except Exception:
                return
            if not f:
                return
            filename, err = self.editor.import_root_file(Path(f.get_path()))
            if err:
                toast(f"Could not import {title.lower()}: {err}")
                return
            data[field] = filename
            row.set_subtitle(filename or "None")
            load_preview(filename or "")
            clear_btn.set_sensitive(True)
            self._save_companion(data)

        def on_choose(_b) -> None:
            dlg = Gtk.FileDialog()
            dlg.set_title(f"Choose {title}")
            filt = Gtk.FileFilter(); filt.set_name("Images")
            for mime in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"):
                filt.add_mime_type(mime)
            dlg.set_default_filter(filt)
            dlg.open(choose_btn.get_root(), None, on_chosen)

        def on_clear(_b) -> None:
            data[field] = None
            row.set_subtitle("None")
            load_preview("")
            clear_btn.set_sensitive(False)
            self._save_companion(data)

        choose_btn.connect("clicked", on_choose)
        clear_btn.connect("clicked", on_clear)
        row.add_suffix(choose_btn)
        row.add_suffix(clear_btn)
        return row

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

    # --- Phase 4: save settings as pack config ----------------------------

    def _build_config_save_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(
            title="Pack Configuration",
            description="Bake your current Edgeware settings into this pack as its "
                        "suggested config (loaded via the pack's \"Load Pack Configuration\").",
        )
        existing = self.editor.config_key_count()
        row = Adw.ActionRow(
            title="Save Current Settings as Pack Config",
            subtitle=f"Pack currently ships {existing} setting{'s' if existing != 1 else ''}."
                     if existing else "Pack has no config.json yet.",
        )
        save_btn = Gtk.Button()
        save_btn.set_child(Adw.ButtonContent(
            label="Save Settings…", icon_name="document-save-symbolic"))
        save_btn.set_valign(Gtk.Align.CENTER)
        save_btn.connect("clicked", lambda _b, r=row: self._on_save_config(r))
        row.add_suffix(save_btn)
        group.add(row)
        page.add(group)

    def _on_save_config(self, row: Adw.ActionRow) -> None:
        from gtk_dialog import ask_yes_no
        from config import load_config

        cfg = load_config()
        # Count what would be written (minus blocked keys) for the prompt.
        from pack.edit import _PACK_CONFIG_BLOCKLIST
        n = len([k for k in cfg if k not in _PACK_CONFIG_BLOCKLIST])
        if not ask_yes_no(
            "Save settings as pack config?",
            f"{n} of your current settings will be written into this pack's "
            "config.json, replacing any existing pack config. Machine- and "
            "safety-specific settings (panic key, safeword, drive path, API keys) "
            "are never included.",
            heading="Save pack config?",
        ):
            return
        err = self.editor.save_config_from(cfg)
        if err:
            toast(f"Could not save pack config: {err}")
            return
        row.set_subtitle(f"Pack currently ships {self.editor.config_key_count()} settings.")
        toast("Pack config saved.")

    # --- Phase 4: corruption editor ---------------------------------------

    def _build_corruption_row(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup(title="Corruption")
        n = self.editor.corruption_level_count()
        row = Adw.ActionRow(
            title="Edit Corruption Levels",
            subtitle=f"{n} level{'s' if n != 1 else ''} defined." if n
                     else "Content that escalates over levels. None defined yet.",
        )
        row.set_activatable(self._push_page is not None)
        if self._push_page is not None:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_valign(Gtk.Align.CENTER)
            row.add_suffix(arrow)
            row.connect("activated", lambda _: self._push_corruption_page())
        group.add(row)
        page.add(group)

    def _push_corruption_page(self) -> None:
        if not self._push_page:
            return
        data = self.editor.get_corruption()
        mood_names = self.editor.mood_names()

        pref = Adw.PreferencesPage()
        pref.set_vexpand(True)

        intro = Adw.PreferencesGroup(
            description="Each level can add or remove moods. Level 1 is the starting "
                        "state; higher levels are reached as corruption advances. "
                        "Mood names must match this pack's moods.",
        )
        pref.add(intro)

        self._corruption_data = data
        self._corruption_mood_names = mood_names
        self._corruption_images = self._pack_image_files()

        levels_group = Adw.PreferencesGroup(title="Levels")
        pref.add(levels_group)
        self._corruption_levels_group = levels_group
        self._corruption_rows: list = []
        self._rebuild_corruption_levels()

        # Add-level button in the header
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add level")
        add_btn.connect("clicked", lambda _b: self._on_add_corruption_level())
        levels_group.set_header_suffix(add_btn)

        back_btn = Gtk.Button()
        back_btn.set_child(Adw.ButtonContent(
            icon_name="go-previous-symbolic", label="Edit Pack"))
        back_btn.set_halign(Gtk.Align.START)
        back_btn.set_margin_start(6)
        back_btn.connect("clicked", lambda _: self._pop_page() if self._pop_page else None)
        top_bar = Gtk.Box(); top_bar.append(back_btn)
        tv = Adw.ToolbarView(); tv.add_top_bar(top_bar); tv.set_content(pref)
        self._push_page(Adw.NavigationPage.new(tv, "Corruption Levels"))

    def _pack_image_files(self) -> list[str]:
        """Image filenames in the pack root (corruption wallpapers live there)."""
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        try:
            return sorted(
                p.name for p in self.editor.pack_dir.iterdir()
                if p.is_file() and p.suffix.lower() in exts
            )
        except Exception:
            return []

    def _corruption_level_keys(self) -> list[int]:
        d = self._corruption_data
        keys = set()
        for section in ("moods", "config", "wallpapers", "names"):
            keys |= {int(k) for k in d.get(section, {}) if k.isdigit()}
        return sorted(keys)

    def _rebuild_corruption_levels(self) -> None:
        for row in self._corruption_rows:
            self._corruption_levels_group.remove(row)
        self._corruption_rows = []
        for level in self._corruption_level_keys() or [1]:
            self._append_corruption_level(level)

    def _append_corruption_level(self, level: int) -> None:
        data = self._corruption_data
        key = str(level)
        mood_entry = data["moods"].setdefault(key, {"add": [], "remove": []})
        mood_entry.setdefault("add", [])
        mood_entry.setdefault("remove", [])

        name = str(data["names"].get(key, ""))
        exp = Adw.ExpanderRow(title=f"Level {level}: {name}" if name else f"Level {level}")
        exp.set_subtitle(f"+{len(mood_entry['add'])} / -{len(mood_entry['remove'])} moods")

        keys = self._corruption_level_keys()

        # Delete button added first → packs rightmost (suffixes fill right-to-left)
        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.add_css_class("destructive-action")
        del_btn.set_tooltip_text("Delete level")
        del_btn.connect("clicked", lambda _b, lv=level: self._on_delete_corruption_level(lv))
        exp.add_suffix(del_btn)

        # Linked ↑↓ pair added second → packs left of delete, visually distinct from expander
        reorder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        reorder_box.add_css_class("linked")
        reorder_box.set_valign(Gtk.Align.CENTER)

        up_btn = Gtk.Button(icon_name="go-up-symbolic")
        up_btn.set_tooltip_text("Move level up")
        up_btn.set_sensitive(level != keys[0])
        up_btn.connect("clicked", lambda _b, lv=level: self._on_move_corruption_level(lv, -1))
        reorder_box.append(up_btn)

        down_btn = Gtk.Button(icon_name="go-down-symbolic")
        down_btn.set_tooltip_text("Move level down")
        down_btn.set_sensitive(level != keys[-1])
        down_btn.connect("clicked", lambda _b, lv=level: self._on_move_corruption_level(lv, +1))
        reorder_box.append(down_btn)

        exp.add_suffix(reorder_box)

        exp.add_row(self._corruption_name_row(level, exp))
        exp.add_row(self._corruption_mood_row(level, "add", "Add moods"))
        exp.add_row(self._corruption_mood_row(level, "remove", "Remove moods"))
        exp.add_row(self._corruption_wallpaper_row(level))

        self._corruption_levels_group.add(exp)
        self._corruption_rows.append(exp)

    def _corruption_name_row(self, level: int, exp: Adw.ExpanderRow) -> Adw.EntryRow:
        """Optional display name for the level. Updates the expander title live."""
        key = str(level)
        row = Adw.EntryRow(title="Level Name (optional)")
        row.set_text(str(self._corruption_data["names"].get(key, "")))

        def on_changed(r: Adw.EntryRow, lv=level, k=key, e=exp) -> None:
            text = r.get_text().strip()
            names = self._corruption_data.setdefault("names", {})
            if text:
                names[k] = text
            else:
                names.pop(k, None)
            e.set_title(f"Level {lv}: {text}" if text else f"Level {lv}")
            self._save_corruption()

        row.connect("changed", on_changed)
        return row

    def _corruption_mood_row(self, level: int, kind: str, title: str) -> Adw.ActionRow:
        """A mood multi-select: shows the chosen moods + a button opening a
        checklist popover of the pack's moods (no freeform typing)."""
        key = str(level)
        row = Adw.ActionRow(title=title)
        selected = self._corruption_data["moods"][key][kind]
        known = set(self.editor.mood_names())
        subtitle_parts = [f"{m} (?)" if m not in known else m for m in selected]
        row.set_subtitle(", ".join(subtitle_parts) if subtitle_parts else "None")

        btn = Gtk.MenuButton(label="Select…")
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_popover(self._mood_select_popover(key, kind, row))
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        return row

    def _mood_select_popover(self, key: str, kind: str, row: Adw.ActionRow) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(8); box.set_margin_end(8)
        box.set_margin_top(8); box.set_margin_bottom(8)

        selected = set(self._corruption_data["moods"][key][kind])
        mood_names = self._corruption_mood_names
        known = set(mood_names)

        if not mood_names:
            box.append(Gtk.Label(label="This pack has no moods."))
        for name in mood_names:
            check = Gtk.CheckButton(label=name)
            check.set_active(name in selected)
            check.connect("toggled", lambda c, n=name, k=key, knd=kind, r=row:
                          self._toggle_corruption_mood(k, knd, n, c.get_active(), r))
            box.append(check)

        # Stale entries: in the level's list but no longer a pack mood.
        stale = [m for m in self._corruption_data["moods"][key][kind] if m not in known]
        if stale:
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            sep.set_margin_top(4); sep.set_margin_bottom(4)
            box.append(sep)
            lbl = Gtk.Label(label="Removed moods (uncheck to clean up):")
            lbl.add_css_class("dim-label")
            lbl.set_xalign(0)
            box.append(lbl)
            for name in stale:
                check = Gtk.CheckButton(label=name)
                check.set_active(True)
                check.add_css_class("dim-label")
                check.connect("toggled", lambda c, n=name, k=key, knd=kind, r=row:
                              self._toggle_corruption_mood(k, knd, n, c.get_active(), r))
                box.append(check)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_max_content_height(280)
        scroller.set_propagate_natural_height(True)
        scroller.set_propagate_natural_width(True)
        scroller.set_child(box)
        pop.set_child(scroller)
        return pop

    def _toggle_corruption_mood(self, key: str, kind: str, name: str,
                                active: bool, row: Adw.ActionRow) -> None:
        lst = self._corruption_data["moods"].setdefault(key, {"add": [], "remove": []})[kind]
        if active and name not in lst:
            lst.append(name)
        elif not active and name in lst:
            lst.remove(name)
        known = set(self.editor.mood_names())
        parts = [f"{m} (?)" if m not in known else m for m in lst]
        row.set_subtitle(", ".join(parts) if parts else "None")
        self._save_corruption()

    def _corruption_wallpaper_row(self, level: int) -> Adw.ActionRow:
        key = str(level)
        current = str(self._corruption_data["wallpapers"].get(key, ""))
        row = Adw.ActionRow(title="Wallpaper")
        row.set_subtitle(current or "None")

        thumb = Gtk.Picture()
        thumb.set_size_request(56, 32)
        thumb.set_content_fit(Gtk.ContentFit.COVER)
        thumb.set_can_shrink(True)
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_valign(Gtk.Align.CENTER)
        frame.set_child(thumb)
        row.add_prefix(frame)
        self._load_wallpaper_thumb(thumb, current)

        choose_btn = Gtk.Button()
        choose_btn.set_child(Adw.ButtonContent(label="Choose…", icon_name="image-x-generic-symbolic"))
        choose_btn.set_valign(Gtk.Align.CENTER)

        def on_pick(name: str, k=key, r=row, t=thumb) -> None:
            self._set_corruption_wallpaper(k, name)
            r.set_subtitle(name or "None")
            self._load_wallpaper_thumb(t, name)

        choose_btn.connect("clicked", lambda _b, k=key, c=current: self._open_wallpaper_picker(on_pick, c))
        row.add_suffix(choose_btn)
        return row

    def _load_wallpaper_thumb(self, picture: Gtk.Picture, filename: str) -> None:
        from gi.repository import GdkPixbuf, Gdk
        if not filename:
            picture.set_paintable(None)
            return
        path = self.editor.pack_dir / filename
        if not path.is_file():
            picture.set_paintable(None)
            return
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 112, 64, True)
            picture.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
        except Exception:
            picture.set_paintable(None)

    def _open_wallpaper_picker(self, on_pick, current: str) -> None:
        from config.gtk_window.image_picker import open_image_picker
        root = self._page.get_root() if self._page else None
        open_image_picker(root, self.editor.pack_dir, current, on_pick,
                           title="Choose Wallpaper")


    def _set_corruption_wallpaper(self, key: str, filename: str) -> None:
        if filename.strip():
            self._corruption_data["wallpapers"][key] = filename.strip()
        else:
            self._corruption_data["wallpapers"].pop(key, None)
        self._save_corruption()

    def _on_move_corruption_level(self, level: int, direction: int) -> None:
        other = level + direction
        if other not in self._corruption_level_keys():
            return
        d = self._corruption_data
        for section in ("moods", "config", "wallpapers", "names"):
            sec = d.get(section, {})
            a = sec.pop(str(level), None)
            b = sec.pop(str(other), None)
            if a is not None:
                sec[str(other)] = a
            if b is not None:
                sec[str(level)] = b
        self._save_corruption()
        self._rebuild_corruption_levels()

    def _on_add_corruption_level(self) -> None:
        keys = self._corruption_level_keys()
        new_level = (max(keys) + 1) if keys else 1
        self._append_corruption_level(new_level)
        self._save_corruption()

    def _on_delete_corruption_level(self, level: int) -> None:
        from gtk_dialog import ask_yes_no
        if not ask_yes_no(
            f"Delete corruption level {level}?",
            "Higher levels are renumbered down to stay contiguous.",
            heading="Delete level?",
        ):
            return
        # Remove the level, then renumber remaining levels to be contiguous.
        d = self._corruption_data
        for section in ("moods", "config", "wallpapers", "names"):
            sec = d.get(section, {})
            remaining = sorted((int(k) for k in sec if k.isdigit()))
            remaining = [n for n in remaining if n != level]
            renumbered = {}
            for new_idx, old in enumerate(remaining, start=1):
                renumbered[str(new_idx)] = sec[str(old)]
            # Keep non-numeric keys (e.g. wallpapers "default").
            for k, v in sec.items():
                if not k.isdigit():
                    renumbered[k] = v
            d[section] = renumbered
        self._save_corruption()
        self._rebuild_corruption_levels()

    def _save_corruption(self) -> None:
        err = self.editor.save_corruption(self._corruption_data)
        if err:
            toast(f"Could not save corruption: {err}")

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

        toast("Migration complete.")
        # Rebuild the editor page in place (no window reload).
        if self._on_migrated:
            self._on_migrated()

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

# Shared tone/style presets for AI generation. The label is shown in the combo;
# the value is the tone instruction fed into the prompt. "Custom…" contributes
# nothing on its own — the free-text box below supplies the direction.
# Tone presets. Each is phrased as how the pack should address the viewer, so the
# model keeps the dominant/second-person voice (it speaks TO the viewer).
_STYLE_PRESETS: dict[str, str] = {
    "Custom…":                  "",
    "Hypnotic / submissive":    "a hypnotic, dominant tone that lulls the viewer into deeper submission",
    "Bratty / teasing":         "a playful, bratty, teasing tone that taunts the viewer",
    "Gentle / loving":          "a soft, affectionate, loving tone that reassures the viewer",
    "Degrading / humiliating":  "a harsh, degrading, humiliating tone that puts the viewer down",
    "Worshipful / addicted":    "demanding the viewer's worship and reinforcing how addicted they are "
                                "(e.g. \"worship me\", \"you can't stop\")",
    "Corruptive / escalating":  "a corruptive tone that escalates and pulls the viewer deeper over time",
}


def _build_style_selector():
    """A reusable style group: a tone-preset combo + a free-text direction box.
    Returns (group_widget, get_direction) where get_direction() resolves the
    chosen preset plus any custom text into one direction string."""
    group = Adw.PreferencesGroup()
    combo = Adw.ComboRow(title="Style", subtitle="Pick a tone, or Custom and write your own")
    combo.set_model(Gtk.StringList.new(list(_STYLE_PRESETS)))
    notes = Adw.EntryRow(title="Direction / theme (optional)")
    group.add(combo)
    group.add(notes)

    names = list(_STYLE_PRESETS)

    def get_direction() -> str:
        preset = _STYLE_PRESETS.get(names[combo.get_selected()], "") if 0 <= combo.get_selected() < len(names) else ""
        extra = notes.get_text().strip()
        return ", ".join(p for p in (preset, extra) if p)

    return group, get_direction


def _conns_from_config(c: dict) -> dict:
    """Connection dict for make_slot_backend, from a config.json dict. Uses only
    the per-type keys (migration already moved the legacy shared connection)."""
    return {
        "ollama_url": c.get("ollamaUrl") or "",
        "openai_url": c.get("openaiUrl") or "",
        "openai_key": c.get("openaiKey") or "",
        "opencode_url": c.get("opencodeUrl") or "",
        "opencode_key": c.get("opencodeKey") or "",
    }


def _make_backend_from_config():
    """Build the pack-edit generation backend from config.json. Returns None if
    the companion is disabled or the resolved backend is scripted."""
    try:
        from config import load_config
        from features.companion.llm import make_slot_backend
        c = load_config()
        if not c.get("companionEnabled"):
            return None
        # Pack-edit slot: its own backend + model, each falling back to the main.
        backend = (c.get("packEditBackend") or "").strip() or c.get("companionBackend", "scripted")
        if (backend or "scripted").lower() == "scripted":
            return None  # scripted can't generate useful content
        model = (c.get("packEditModel") or "").strip() or c.get("companionModel") or None
        return make_slot_backend(backend, model or "", _conns_from_config(c))
    except Exception:
        return None


def _open_generate_dialog(
    anchor: Gtk.Widget,
    list_type: str,
    context: str,
    appender: list,
    *,
    type_hint: str = "",
    pack_desc: str = "",
) -> None:
    """Open a modal generation window. `appender` is a one-element list
    containing a `bulk_append(items)` fn from make_string_list_group.
    `type_hint` describes what this list type is; `pack_desc` is the pack's
    own description — both fed to the model for on-theme output."""
    from threading import Thread

    dialog = Adw.Dialog()
    dialog.set_title(f"Generate {list_type}")
    dialog.set_content_width(500)
    dialog.set_content_height(540)
    root = anchor.get_root()

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(16); box.set_margin_end(16)
    box.set_margin_top(16);  box.set_margin_bottom(16)

    ctx_lbl = Gtk.Label(label=f"Context: {context}")
    ctx_lbl.add_css_class("dim-label")
    ctx_lbl.set_halign(Gtk.Align.START)
    box.append(ctx_lbl)

    style_group, get_direction = _build_style_selector()
    box.append(style_group)

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
    cancel_btn.connect("clicked", lambda _: dialog.close())
    add_btn = Gtk.Button()
    add_btn.set_sensitive(False)
    btn_row.append(cancel_btn)
    btn_row.append(add_btn)
    box.append(btn_row)

    _generated: list[list[str]] = [[]]  # mutable container

    def do_generate(_b) -> None:
        theme = get_direction()
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

        what = type_hint or f"{list_type.lower()} entries"
        lines = [
            f"You are a creative writer for an adult popup software pack ({context}).",
        ]
        if pack_desc.strip():
            lines.append(f"The pack's theme and description: {pack_desc.strip()}")
        lines.append(f"Your task: write {what}.")
        # Voice: the pack speaks TO the viewer, never as the viewer.
        lines.append(
            "Crucial: every entry is spoken BY the pack TO the viewer, addressing them "
            "in the second person (\"you\"). The pack is the dominant/controlling voice; "
            "the viewer is the one being teased, commanded, or affected. For example write "
            "\"Worship me\" or \"You can't stop\", NOT \"I worship you\" or \"I'm hooked\". "
            "Never write from the viewer's first-person perspective."
        )
        lines.append(
            f"Generate exactly {count} entries that fit this pack's theme. "
            f"Output one entry per line, with no numbering, no bullet points, no "
            f"preamble, and no empty lines — just the {count} entries."
        )
        system = "\n".join(lines)
        user_msg = (
            f"Extra direction: {theme}. " if theme else ""
        ) + f"Write {count} {list_type.lower()} entries now, on theme for this pack."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        def on_token(tok: str) -> None:
            GLib.idle_add(_buf_append, buf, tok)

        def on_done(full: str) -> None:
            items = [_clean_generated_line(ln) for ln in full.splitlines() if ln.strip()]
            items = [it for it in items if it][:count]
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
        dialog.close()

    gen_btn.connect("clicked", do_generate)
    add_btn.connect("clicked", do_add)

    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(box)
    dialog.set_child(tv)
    dialog.present(root)


def _buf_append(buf: Gtk.TextBuffer, text: str) -> bool:
    buf.insert(buf.get_end_iter(), text)
    return False


def _clean_generated_line(line: str) -> str:
    """Strip leading list markers a model may add despite instructions
    ("1. ", "1) ", "- ", "* ", "• ") plus surrounding quotes/whitespace."""
    import re
    s = line.strip()
    s = re.sub(r'^\s*(?:\d+[.)]|[-*•])\s+', '', s)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def _open_prompt_generate_dialog(
    anchor: Gtk.Widget,
    context: str,
    pack_desc: str,
    target_buf: Gtk.TextBuffer,
) -> None:
    """Generate a single system-prompt block (not a list) for the companion and,
    on accept, replace `target_buf`'s contents with it."""
    from threading import Thread

    dialog = Adw.Dialog()
    dialog.set_title("Generate System Prompt")
    dialog.set_content_width(540)
    dialog.set_content_height(560)
    root = anchor.get_root()

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(16); box.set_margin_end(16)
    box.set_margin_top(16);  box.set_margin_bottom(16)

    ctx_lbl = Gtk.Label(label=f"Context: {context}")
    ctx_lbl.add_css_class("dim-label")
    ctx_lbl.set_halign(Gtk.Align.START)
    ctx_lbl.set_wrap(True)
    box.append(ctx_lbl)

    style_group, get_direction = _build_style_selector()
    box.append(style_group)

    gen_btn = Gtk.Button(label="Generate")
    gen_btn.add_css_class("suggested-action")
    box.append(gen_btn)

    tv = Gtk.TextView()
    tv.set_editable(False)
    tv.set_wrap_mode(Gtk.WrapMode.WORD)
    tv.set_top_margin(8); tv.set_bottom_margin(8)
    tv.set_left_margin(8); tv.set_right_margin(8)
    buf = tv.get_buffer()
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_vexpand(True)
    sw.set_min_content_height(240)
    sw.set_child(tv)
    frame = Gtk.Frame(); frame.add_css_class("card"); frame.set_child(sw)
    box.append(frame)

    btn_row = Gtk.Box(spacing=8)
    btn_row.set_halign(Gtk.Align.END)
    cancel_btn = Gtk.Button(label="Cancel")
    cancel_btn.connect("clicked", lambda _: dialog.close())
    use_btn = Gtk.Button(label="Use this prompt")
    use_btn.set_sensitive(False)
    btn_row.append(cancel_btn)
    btn_row.append(use_btn)
    box.append(btn_row)

    def do_generate(_b) -> None:
        theme = get_direction()
        buf.set_text("")
        gen_btn.set_sensitive(False)
        use_btn.set_sensitive(False)

        backend = _make_backend_from_config()
        if backend is None:
            buf.set_text(
                "No LLM backend available.\n\nEnable the AI Companion and configure "
                "Ollama or an OpenAI-compatible endpoint in Settings → Companion."
            )
            gen_btn.set_sensitive(True)
            return

        system = (
            "You write system prompts that define the personality of an AI companion "
            "character for an adult popup software pack. Output ONLY the system prompt "
            "text itself — a vivid second-person character definition the model will be "
            "given (tone, personality, how it speaks to and treats the user). No preamble, "
            "no headings, no quotes around it."
        )
        user = f"The pack: {context}."
        if pack_desc.strip():
            user += f" Pack description: {pack_desc.strip()}."
        if theme:
            user += f" Desired personality: {theme}."
        user += " Write the companion's system prompt now."

        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]

        def on_token(tok: str) -> None:
            GLib.idle_add(_buf_append, buf, tok)

        def on_done(_full: str) -> None:
            GLib.idle_add(use_btn.set_sensitive, True)
            GLib.idle_add(gen_btn.set_sensitive, True)

        def on_error(exc: Exception) -> None:
            GLib.idle_add(_buf_append, buf, f"\n\nError: {exc}")
            GLib.idle_add(gen_btn.set_sensitive, True)

        Thread(target=backend.stream, args=(messages, on_token, on_done, on_error),
               daemon=True).start()

    def do_use(_b) -> None:
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if text:
            target_buf.set_text(text)  # fires the buffer's changed handler -> autosave
        dialog.close()

    gen_btn.connect("clicked", do_generate)
    use_btn.connect("clicked", do_use)

    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    tv.set_content(box)
    dialog.set_child(tv)
    dialog.present(root)
