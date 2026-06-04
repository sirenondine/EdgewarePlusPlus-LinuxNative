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

"""Resolve Edgeware's Discord rich-presence image assets to previewable URLs.

The runtime sets the presence image by asset *name* (e.g. "goon_img") against
the Edgeware Discord application; Discord hosts the actual images on its CDN.
This module fetches the application's public asset list so the editor can show
real thumbnails instead of opaque names. Network, blocking — call off-thread.
"""

import logging

# The Edgeware Discord application id (see features.misc.handle_discord).
APP_ID = "820204081410736148"

_cache: dict[str, str] | None = None


def fetch_assets() -> dict[str, str]:
    """Return {asset_name: cdn_png_url}, or {} on failure. Cached after first
    success. Blocking — run on a worker thread."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        import requests
        r = requests.get(
            f"https://discord.com/api/v9/oauth2/applications/{APP_ID}/assets",
            timeout=10,
        )
        r.raise_for_status()
        out: dict[str, str] = {}
        for asset in r.json():
            name = asset.get("name")
            asset_id = asset.get("id")
            if name and asset_id:
                out[name] = f"https://cdn.discordapp.com/app-assets/{APP_ID}/{asset_id}.png"
        _cache = out
        return out
    except Exception as e:
        logging.warning(f"Could not fetch Discord assets: {e}")
        return {}
