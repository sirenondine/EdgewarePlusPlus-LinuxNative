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

# Thin wrapper over the `booru` library. Adds site selection (the popup path was
# hard-wired to Gelbooru) and search/preview helpers used by both the runtime
# image popups and the config preview grid. All network calls are blocking and
# must run on a worker thread.

import asyncio
import json
import logging
import random

# Curated subset of the sites the `booru` package exposes, by config key.
SITE_CLASSES = {
    "gelbooru": "Gelbooru",
    "rule34": "Rule34",
    "safebooru": "Safebooru",
    "danbooru": "Danbooru",
    "e621": "E621",
    "e926": "E926",
    "yandere": "Yandere",
    "konachan": "Konachan",
    "xbooru": "Xbooru",
    "realbooru": "Realbooru",
    "tbib": "Tbib",
    "hypnohub": "Hypnohub",
}
SITE_NAMES = list(SITE_CLASSES.keys())
DEFAULT_SITE = "gelbooru"


def _client(site: str, api_key: str = "", user_id: str = ""):
    import booru
    cls_name = SITE_CLASSES.get((site or DEFAULT_SITE).lower(), SITE_CLASSES[DEFAULT_SITE])
    cls = getattr(booru, cls_name)
    # Auth-capable sites take (api_key, user_id|login) positionally; sites
    # without auth (e.g. Rule34) take no args and raise TypeError, so fall back.
    if api_key or user_id:
        try:
            return cls(api_key, user_id)
        except TypeError:
            pass
    return cls()


RATINGS = ["any", "safe", "questionable", "explicit"]


def _split(value: str) -> list[str]:
    return [t for t in (value or "").replace(">", " ").split() if t]


def build_query(tags: str, exclude: str = "", rating: str = "any") -> str:
    """Compose a booru query: include tags, minus excluded tags (-tag), plus an
    optional rating: filter. The historical "all" default means "anything", so
    it is dropped (boorus treat it as a literal, non-existent tag)."""
    parts = [t for t in _split(tags) if t.lower() != "all"]
    parts += [f"-{t}" for t in _split(exclude)]
    if rating and rating != "any":
        parts.append(f"rating:{rating}")
    return " ".join(parts)


def search(site: str, tags: str, limit: int = 12, page: int = 1, api_key: str = "",
           user_id: str = "", exclude: str = "", rating: str = "any") -> list[dict]:
    """Return up to `limit` post dicts from `site` for `tags` minus `exclude`,
    optionally filtered to a `rating`. Empty list on no results or error.
    Blocking — call off the main thread."""
    try:
        client = _client(site, api_key, user_id)
        query = build_query(tags, exclude, rating)
        result = asyncio.run(client.search(query=query, limit=limit, page=page))
        if isinstance(result, str):
            result = json.loads(result)
        return result or []
    except Exception as e:
        logging.warning(f"Booru search failed ({site}, '{tags}'): {e}")
        return []


def thumb_url(post: dict) -> str | None:
    return post.get("preview_url") or post.get("sample_url") or post.get("file_url")


def random_image_url(site: str, tags: str, limit: int = 20, api_key: str = "",
                     user_id: str = "", exclude: str = "", rating: str = "any") -> str | None:
    """Pick a random full-resolution image URL for `tags`, or None."""
    posts = search(site, tags, limit=limit, api_key=api_key, user_id=user_id, exclude=exclude, rating=rating)
    urls = [p.get("file_url") for p in posts if p.get("file_url")]
    return random.choice(urls) if urls else None


def fetch_bytes(url: str, timeout: int = 10) -> bytes:
    import requests
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content
