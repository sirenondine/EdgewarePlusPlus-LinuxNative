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

from config.gtk_window.utils import config
from config.gtk_window.widgets import AdwComboRow, AdwEntryRow, AdwSliderRow, AdwSwitchRow, bind_visibility, make_string_list_group
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
        group.add(AdwSliderRow(
            "Booru Image Chance", vars.booru_chance, 0, 100, unit="%",
            subtitle="How often an image popup pulls from the booru instead of the pack."))
        group.add(AdwSwitchRow(
            "Use Images", vars.booru_images, subtitle="Pull still images (JPG/PNG)."))
        group.add(AdwSwitchRow(
            "Use GIFs", vars.booru_gifs, subtitle="Pull animated GIFs (played via the video pipeline)."))
        group.add(AdwSwitchRow(
            "Use Videos", vars.booru_videos, subtitle="Pull videos (MP4/WebM), played with sound."))
        group.add(AdwComboRow(
            "Site", vars.booru_site,
            {name: name.capitalize() for name in booru.SITE_NAMES}))
        url_row = AdwEntryRow("Custom Endpoint URL", vars.booru_custom_url)
        detect_btn = Gtk.Button(label="Detect", valign=Gtk.Align.CENTER)
        detect_btn.set_tooltip_text("Probe the URL and set the API type automatically")
        detect_btn.connect("clicked", lambda _b: self._on_detect_api())
        url_row.add_suffix(detect_btn)
        group.add(url_row)
        api_row = AdwComboRow(
            "Custom API Type", vars.booru_api_type,
            {t: t.capitalize() for t in booru.API_TYPES})
        group.add(api_row)
        # Only relevant when the "custom" site is selected.
        bind_visibility(url_row, vars.booru_site, lambda v: v == "custom")
        bind_visibility(api_row, vars.booru_site, lambda v: v == "custom")

        # Optional credentials (e.g. Gelbooru API key + user id, Danbooru
        # api key + login). Left blank for anonymous access.
        creds = Adw.PreferencesGroup(
            title="Credentials",
            description="Optional for many sites, but Gelbooru and Danbooru now require BOTH an API key AND your user id (Danbooru: login) — an API key alone is ignored. Find them on your account/options page. Leave blank for anonymous sites.")
        self.add(creds)
        creds.add(AdwEntryRow("API key", vars.booru_api_key, password=True))
        creds.add(AdwEntryRow("User ID / Login", vars.booru_user_id))

        self.add(self._make_tag_list_group(
            "Tags", "tagList", "all",
            'Posts must match these tags. Use "all" (or leave empty) for anything.'))
        self.add(self._make_tag_list_group(
            "Excluded Tags", "booruExclude", "",
            "Posts matching any of these tags are skipped (sent as -tag)."))

        rating_group = Adw.PreferencesGroup(title="Rating and Sort")
        self.add(rating_group)
        rating_group.add(AdwComboRow(
            "Rating", vars.booru_rating,
            {r: r.capitalize() for r in booru.RATINGS}))
        rating_group.add(AdwComboRow(
            "Sort", vars.booru_sort,
            {k: v for k, v in booru.SORT_OPTIONS.items()}))

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

    def _on_detect_api(self) -> None:
        url = self._vars.booru_custom_url.get() or ""
        if not url:
            self._status.set_text("Enter a custom endpoint URL first.")
            return
        self._status.set_text(f"Detecting API type for {url}…")

        def work() -> None:
            kind = booru.detect_api_type(url)
            GLib.idle_add(self._apply_detected_api, kind)
        threading.Thread(target=work, daemon=True).start()

    def _apply_detected_api(self, kind) -> bool:
        if kind in booru.API_TYPES:
            self._vars.booru_api_type.set(kind)  # combo resyncs via its trace
            self._vars.booru_site.set("custom")
            self._status.set_text(f"Detected API type: {kind}. Site set to custom.")
        else:
            self._status.set_text("Could not detect the API type — set it manually.")
        return False

    # ---- Preview handlers ------------------------------------------------
    def _on_preview(self, _btn: Gtk.Button) -> None:
        site = self._vars.booru_site.get() or booru.DEFAULT_SITE
        api_key = self._vars.booru_api_key.get() or ""
        user_id = self._vars.booru_user_id.get() or ""
        exclude = config.get("booruExclude", "")
        rating = self._vars.booru_rating.get() or "any"
        self._custom_url = self._vars.booru_custom_url.get() or ""
        self._api_type = self._vars.booru_api_type.get() or "danbooru"
        # Remember whether this site needs credentials we don't fully have, to
        # give a useful message if it returns nothing.
        self._needs_creds = site in ("gelbooru", "danbooru") and not (api_key and user_id)
        self._last_site = f"custom ({self._custom_url})" if site == "custom" else site
        tags = config.get("tagList", "").replace(">", " ").strip()
        child = self._flow.get_first_child()
        while child:
            self._flow.remove(child)
            child = self._flow.get_first_child()
        self._preview_btn.set_sensitive(False)
        self._spinner.start()
        sort = self._vars.booru_sort.get() or ""
        self._status.set_text(f"Searching {site} for: {tags or '(all)'}…")
        threading.Thread(target=self._preview_worker,
                         args=(site, tags, api_key, user_id, exclude, rating, sort,
                               self._custom_url, self._api_type), daemon=True).start()

    def _preview_worker(self, site: str, tags: str, api_key: str, user_id: str, exclude: str,
                        rating: str, sort: str, custom_url: str, api_type: str) -> None:
        results = booru.search(site, tags, limit=PREVIEW_COUNT, api_key=api_key,
                               user_id=user_id, exclude=exclude, rating=rating,
                               custom_url=custom_url, api_type=api_type, sort=sort)
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
        if count:
            msg = f"{count} result(s)."
        elif getattr(self, "_needs_creds", False):
            msg = f"No results. {self._last_site.capitalize()} requires BOTH an API key and a user id/login — fill both under Credentials."
        else:
            msg = "No results — try different tags or another site."
        self._status.set_text(msg)
        return False

    def _make_tag_list_group(self, title: str, config_key: str, default: str, description: str) -> Adw.PreferencesGroup:
        """A reusable add/remove/reset tag list bound to a ">"-joined config key.
        Used for both the include tags and the exclude tags."""
        def on_change(items: list[str]) -> None:
            config[config_key] = ">".join(items)
            # These tag lists write straight to the config dict (they aren't
            # ConfigVars), so the autosave — which only fires on ConfigVar
            # changes — won't see the edit. Persist it explicitly.
            from config.gtk_window.utils import persist
            persist(self._vars)

        return make_string_list_group(
            title, description,
            initial=[t for t in config.get(config_key, "").split(">") if t],
            on_change=on_change,
            add_prompt="Tag name (or space-separated tags)",
            reset_to=(default.split(">") if default else []),
        )
