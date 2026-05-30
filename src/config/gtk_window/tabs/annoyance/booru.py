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

import threading

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, GLib, Gtk

from config.gtk_window.toast import name_popover
from config.gtk_window.utils import config
from config.gtk_window.widgets import AdwComboRow, AdwSwitchRow
from config.vars import Vars
from features import booru

BOORU_TEXT = (
    "Pull images from a booru at runtime instead of (or alongside) the pack. "
    "Each popup fetches over the network, so a high popup rate can be heavy. "
    "Use Preview below to check your tags return results before enabling."
)
PREVIEW_COUNT = 12
THUMB_SIZE = 120


class BooruTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self._vars = vars

        group = Adw.PreferencesGroup(title="Booru Settings", description=BOORU_TEXT)
        self.add(group)
        group.add(AdwSwitchRow("Download from Booru", vars.booru_download))
        group.add(AdwComboRow(
            "Site", vars.booru_site,
            {name: name.capitalize() for name in booru.SITE_NAMES}))

        tags_group = Adw.PreferencesGroup(title="Tags")
        self.add(tags_group)

        tags = [t for t in config.get("tagList", "").split(">") if t]
        self._tag_store = Gtk.StringList.new(tags)
        self._tag_selection = Gtk.SingleSelection.new(self._tag_store)
        self._tag_selection.connect("notify::selected", self._update_buttons)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        tag_list = Gtk.ListView.new(self._tag_selection, factory)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(180)
        scroller.set_child(tag_list)
        list_frame = Gtk.Frame()
        list_frame.add_css_class("card")
        list_frame.set_child(scroller)
        tags_group.add(list_frame)

        # Header suffix buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add tag")
        add_btn.connect("clicked", self._on_add)
        btn_row.append(add_btn)
        self._remove_btn = Gtk.Button(icon_name="list-remove-symbolic")
        self._remove_btn.set_tooltip_text("Remove selected tag")
        self._remove_btn.connect("clicked", self._on_remove)
        self._remove_btn.set_sensitive(False)
        btn_row.append(self._remove_btn)
        reset_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        reset_btn.set_tooltip_text("Reset to default tags")
        reset_btn.connect("clicked", self._on_reset)
        btn_row.append(reset_btn)
        tags_group.set_header_suffix(btn_row)

        # ---- Preview -----------------------------------------------------
        preview_group = Adw.PreferencesGroup(
            title="Preview", description="Fetch a few example images for the current site and tags.")
        self.add(preview_group)

        self._preview_btn = Gtk.Button(label="Preview")
        self._preview_btn.add_css_class("suggested-action")
        self._preview_btn.connect("clicked", self._on_preview)
        self._spinner = Gtk.Spinner()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(self._spinner)
        head.append(self._preview_btn)
        preview_group.set_header_suffix(head)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("dim-label")
        self._status.set_margin_bottom(6)
        preview_group.add(self._status)

        self._flow = Gtk.FlowBox()
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_min_children_per_line(2)
        self._flow.set_max_children_per_line(6)
        self._flow.set_row_spacing(6)
        self._flow.set_column_spacing(6)
        flow_scroll = Gtk.ScrolledWindow()
        flow_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        flow_scroll.set_min_content_height(280)
        flow_scroll.set_child(self._flow)
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(flow_scroll)
        preview_group.add(frame)

    # ---- Preview handlers ------------------------------------------------
    def _on_preview(self, _btn: Gtk.Button) -> None:
        site = self._vars.booru_site.get() or booru.DEFAULT_SITE
        tags = config.get("tagList", "").replace(">", " ").strip()
        child = self._flow.get_first_child()
        while child:
            self._flow.remove(child)
            child = self._flow.get_first_child()
        self._preview_btn.set_sensitive(False)
        self._spinner.start()
        self._status.set_text(f"Searching {site} for: {tags or '(all)'}…")
        threading.Thread(target=self._preview_worker, args=(site, tags), daemon=True).start()

    def _preview_worker(self, site: str, tags: str) -> None:
        results = booru.search(site, tags, limit=PREVIEW_COUNT)
        shown = 0
        for post in results:
            url = booru.thumb_url(post)
            if not url:
                continue
            try:
                data = booru.fetch_bytes(url)
            except Exception:
                continue
            GLib.idle_add(self._add_thumb, data, post)
            shown += 1
        GLib.idle_add(self._preview_done, shown)

    def _add_thumb(self, data: bytes, post: dict) -> bool:
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
        except Exception:
            return False
        picture = Gtk.Picture.new_for_pixbuf(pixbuf)
        picture.set_size_request(THUMB_SIZE, THUMB_SIZE)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.add_css_class("card")
        score = post.get("score")
        rating = post.get("rating")
        picture.set_tooltip_text(f"score {score} · rating {rating}" if score is not None else str(rating or ""))
        self._flow.append(picture)
        return False

    def _preview_done(self, count: int) -> bool:
        self._spinner.stop()
        self._preview_btn.set_sensitive(True)
        self._status.set_text(
            f"{count} result(s)." if count else "No results — try different tags or another site.")
        return False

    def _on_add(self, btn: Gtk.Button) -> None:
        name_popover(btn, "Tag name (or space-separated tags)", self._add_tag)

    def _add_tag(self, tag: str) -> None:
        current = config.get("tagList", "")
        config["tagList"] = f"{current}>{tag}" if current else tag
        self._tag_store.append(tag)

    def _update_buttons(self, selection, _param=None) -> None:
        pos = selection.get_selected()
        # pos 0 is "all" — don't allow removing it
        self._remove_btn.set_sensitive(
            pos != Gtk.INVALID_LIST_POSITION and pos > 0
        )

    def _on_remove(self, _btn: Gtk.Button) -> None:
        pos = self._tag_selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION and pos > 0:
            tag = self._tag_store.get_string(pos)
            current = config.get("tagList", "")
            config["tagList"] = current.replace(f">{tag}", "")
            self._tag_store.remove(pos)

    def _on_reset(self, _btn: Gtk.Button) -> None:
        while self._tag_store.get_n_items() > 0:
            self._tag_store.remove(0)
        self._tag_store.append("all")
        config["tagList"] = "all"

    @staticmethod
    def _on_setup(_factory, item) -> None:
        lbl = Gtk.Label(xalign=0, wrap=True)
        lbl.set_margin_start(8)
        lbl.set_margin_top(4)
        lbl.set_margin_bottom(4)
        item.set_child(lbl)

    @staticmethod
    def _on_bind(_factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())
