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
import hashlib
import json
import logging
import random
import re
import threading
import time

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
SITE_NAMES = [*SITE_CLASSES.keys(), "custom"]
DEFAULT_SITE = "gelbooru"

# Public web domain for each built-in site, used to build a link back to the
# post page (post_url). Kept alongside SITE_CLASSES so the two stay in sync.
SITE_DOMAINS = {
    "gelbooru": "gelbooru.com",
    "rule34": "rule34.xxx",
    "safebooru": "safebooru.org",
    "danbooru": "danbooru.donmai.us",
    "e621": "e621.net",
    "e926": "e926.net",
    "yandere": "yande.re",
    "konachan": "konachan.com",
    "xbooru": "xbooru.com",
    "realbooru": "realbooru.com",
    "tbib": "tbib.org",
    "hypnohub": "hypnohub.net",
}

# Custom-endpoint API flavours. Most self-hosted / alt boorus run one of these.
API_TYPES = ["danbooru", "gelbooru", "moebooru"]

_HEADERS = {"User-Agent": "EdgewarePP/1.0"}

# ---------------------------------------------------------------------------
# PoW (Proof-of-Work) anti-bot support
# ---------------------------------------------------------------------------
# Some booru endpoints require solving a SHA1 hashcash challenge before they
# serve API responses.  The solved cookie typically lasts ~7 days.
_pow_sessions: dict = {}
_pow_lock = threading.Lock()


def _solve_pow_challenge(base_url: str):
    """Solve a PoW challenge and return a session with the anti-bot cookie, or
    None on failure.  Blocking — call off the main thread."""
    import requests
    base = base_url.rstrip("/")
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})

    r = sess.get(f"{base}/", timeout=15)
    html = r.text

    seed_m = re.search(r'const powSeed = "([^"]+)"', html)
    cid_m = re.search(r'const challenge_id = "([^"]+)"', html)
    cgen_m = re.search(r'const challenge_generated = "([^"]+)"', html)
    cexp_m = re.search(r'const challenge_cookie_expires = "([^"]+)"', html)
    post_to_m = re.search(r'const post_to = "([^"]+)"', html)
    delay_m = re.search(r'const delay = (\d+)', html)

    if seed_m is None or cid_m is None or cgen_m is None or cexp_m is None or post_to_m is None or delay_m is None:
        logging.warning(f"booru PoW: could not parse challenge from {base}")
        return None

    seed = seed_m.group(1)
    challenge_id = cid_m.group(1)
    challenge_generated = cgen_m.group(1)
    challenge_cookie_expires = cexp_m.group(1)
    post_to = post_to_m.group(1)
    delay = int(delay_m.group(1))

    # SHA1 hashcash: find nonce where sha1(seed + ":" + nonce) starts w/ "00000"
    nonce = 0
    prefix = "00000"
    while True:
        candidate = f"{seed}:{nonce}"
        h = hashlib.sha1(candidate.encode()).hexdigest()
        if h.startswith(prefix):
            break
        nonce += 1

    logging.info(f"booru PoW: solved (nonce={nonce}, iterations={nonce + 1})")

    time.sleep(delay + 0.5)

    payload = {
        "challenge_id": challenge_id,
        "challenge_generated": challenge_generated,
        "challenge_cookie_expires": challenge_cookie_expires,
        "pow_nonce": str(nonce),
        "pow_hash": h,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Verification-Challenge": "1",
        "Origin": f"https://{post_to}",
        "Referer": f"https://{post_to}/",
    }
    r2 = sess.post(f"https://{post_to}/", json=payload, headers=headers, timeout=15)
    if r2.status_code != 200:
        logging.warning(f"booru PoW: submission failed (HTTP {r2.status_code})")
        return None

    expiry = float(challenge_cookie_expires)
    with _pow_lock:
        _pow_sessions[base] = (sess, expiry)
    return sess


def _get_pow_session(base_url: str):
    """Return a cached PoW-authenticated session, or solve the challenge to
    create one."""
    base = base_url.rstrip("/")
    with _pow_lock:
        entry = _pow_sessions.get(base)
        if entry:
            sess, expiry = entry
            if time.time() < expiry - 60:
                return sess
    return _solve_pow_challenge(base_url)


def _has_pow_challenge(url: str) -> bool:
    """Quick check if *url* serves a PoW challenge page."""
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        return "powSeed" in r.text and "challenge-checkbox" in r.text
    except Exception:
        return False


def _get_json(url: str, params: dict, timeout: int = 8, label: str = "booru"):
    """GET `url` and return parsed JSON, or None — logging the HTTP status,
    content type and any failure so booru problems are diagnosable from the log
    rather than failing silently."""
    import requests
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    except Exception as e:
        logging.warning(f"{label}: request to {url} failed: {e}")
        return None
    ctype = r.headers.get("content-type", "?")
    if r.status_code != 200:
        logging.warning(f"{label}: {url} -> HTTP {r.status_code} ({ctype})")
        return None
    if "json" not in ctype:
        logging.warning(f"{label}: {url} -> non-JSON response ({ctype}); wrong endpoint or API type?")
        return None
    try:
        return r.json()
    except Exception as e:
        logging.warning(f"{label}: {url} -> invalid JSON: {e}")
        return None


def detect_api_type(base_url: str) -> str | None:
    """Probe a custom endpoint and guess its API flavour (danbooru / moebooru /
    gelbooru), or None. Blocking — call off the main thread."""
    base = (base_url or "").rstrip("/")
    if not base:
        return None
    if _has_pow_challenge(base):
        logging.info(f"booru detect: {base} has PoW challenge — mapped to danbooru")
        return "danbooru"
    probes = [
        ("danbooru", f"{base}/posts.json", {"limit": 1}, list),
        ("moebooru", f"{base}/post.json", {"limit": 1}, list),
        ("gelbooru", f"{base}/index.php",
         {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": 1}, (list, dict)),
    ]
    for kind, url, params, shape in probes:
        data = _get_json(url, params, timeout=6, label=f"booru detect ({kind})")
        if isinstance(data, shape):
            logging.info(f"booru detect: {base} looks like {kind}")
            return kind
    logging.info(f"booru detect: could not identify API type for {base}")
    return None


def _custom_search(base_url: str, api_type: str, query: str, limit: int, page: int,
                   api_key: str = "", user_id: str = "") -> list[dict]:
    """Query an arbitrary booru endpoint (Danbooru / Moebooru / Gelbooru JSON
    API), normalising results so thumb_url()/file_url work like the built-ins.
    Sort is already baked into `query` as a metatag by the caller."""
    base = (base_url or "").rstrip("/")
    label = f"booru custom ({api_type})"
    if api_type == "gelbooru":
        params = {"page": "dapi", "s": "post", "q": "index", "json": "1",
                  "tags": query, "limit": limit, "pid": max(0, page - 1)}
        if api_key and user_id:
            params.update({"api_key": api_key, "user_id": user_id})
        data = _get_json(f"{base}/index.php", params, label=label)
        posts = data.get("post", []) if isinstance(data, dict) else (data or [])
        return [p for p in posts if isinstance(p, dict) and p.get("file_url")]
    if api_type == "moebooru":
        # Moebooru (konachan, yande.re, sakuga, ...): /post.json, anon read.
        params = {"tags": query, "limit": limit, "page": page}
        posts = _get_json(f"{base}/post.json", params, label=label) or []
        return [p for p in posts if isinstance(p, dict) and p.get("file_url")]
    # Danbooru-style (posts.json). file_url / preview_file_url / large_file_url.
    params = {"tags": query, "limit": limit, "page": page}
    if api_key and user_id:
        params.update({"login": user_id, "api_key": api_key})

    # Some boorus require PoW authentication — handle transparently.
    if _has_pow_challenge(base):
        sess = _get_pow_session(base)
        if sess is None:
            return []
        r = sess.get(f"{base}/posts.json", params=params, timeout=10)
        if r.status_code != 200:
            logging.warning(f"{label}: HTTP {r.status_code}")
            return []
        raw = r.json() if "json" in r.headers.get("content-type", "") else []
    else:
        raw = _get_json(f"{base}/posts.json", params, label=label) or []

    out = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict) or not p.get("file_url"):
            continue
        p.setdefault("preview_url", p.get("preview_file_url"))
        p.setdefault("sample_url", p.get("large_file_url"))
        out.append(p)
    return out


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

SORT_OPTIONS = {
    "": "Default (newest first)",
    "id_asc": "Oldest first",
    "score": "Best rated",
    "mpixels": "Largest",
    "random": "Random",
}

# Sort is expressed as a query metatag, and the spelling differs per engine.
# (Gelbooru: sort:<field>:<dir>; Danbooru/Moebooru: order:<field>.) An empty
# string means the engine has no equivalent, so the sort is skipped.
_SORT_TOKENS = {
    "gelbooru": {"id_asc": "sort:id:asc", "score": "sort:score:desc", "mpixels": "", "random": "sort:random"},
    "danbooru": {"id_asc": "order:id_asc", "score": "order:score", "mpixels": "order:mpixels", "random": "order:random"},
    "moebooru": {"id_asc": "order:id", "score": "order:score", "mpixels": "order:mpixels", "random": "order:random"},
}

# Engine each built-in site runs, so the right sort metatag is used.
_SITE_ENGINE = {
    "gelbooru": "gelbooru", "rule34": "gelbooru", "safebooru": "gelbooru",
    "xbooru": "gelbooru", "realbooru": "gelbooru", "tbib": "gelbooru",
    "danbooru": "danbooru", "e621": "danbooru", "e926": "danbooru", "hypnohub": "danbooru",
    "yandere": "moebooru", "konachan": "moebooru",
}


def _sort_tag(engine: str, sort_key: str) -> str:
    """The query metatag for `sort_key` on `engine` ('' if unsupported/none)."""
    return _SORT_TOKENS.get(engine, {}).get(sort_key, "")


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
           user_id: str = "", exclude: str = "", rating: str = "any",
           custom_url: str = "", api_type: str = "danbooru", sort: str = "") -> list[dict]:
    """Return up to `limit` post dicts from `site` for `tags` minus `exclude`,
    optionally filtered to a `rating`. `site` may be "custom" to query an
    arbitrary endpoint (custom_url + api_type). Empty list on no results or
    error. Blocking — call off the main thread."""
    target = f"custom:{custom_url} ({api_type})" if site == "custom" else site
    try:
        query = build_query(tags, exclude, rating)
        # Sort is a query metatag; its spelling depends on the engine.
        engine = api_type if site == "custom" else _SITE_ENGINE.get(site, "gelbooru")
        token = _sort_tag(engine, sort)
        if token:
            query = f"{query} {token}".strip()
        logging.debug(f"booru search: {target} query={query!r} limit={limit} page={page}")
        if site == "custom":
            if not custom_url:
                logging.warning("booru search: site is 'custom' but no custom URL is set.")
                return []
            result = _custom_search(custom_url, api_type, query, limit, page, api_key, user_id)
        else:
            # The booru lib has no sort param; it randomises by default, so only
            # let it shuffle when the user actually picked random.
            client = _client(site, api_key, user_id)
            result = asyncio.run(client.search(query=query, limit=limit, page=page, random=(sort == "random")))
            if isinstance(result, str):
                result = json.loads(result)
            result = result or []
        if sort == "random":
            random.shuffle(result)
        if not result:
            logging.info(f"booru search: 0 results from {target} for query {query!r}")
        else:
            logging.info(f"booru search: {len(result)} result(s) from {target} for query {query!r}")
        return result
    except Exception as e:
        logging.warning(f"booru search failed ({target}, '{tags}'): {e}")
        return []


def thumb_url(post: dict) -> str | None:
    return post.get("preview_url") or post.get("sample_url") or post.get("file_url")


def _post_page(base: str, engine: str, post_id) -> str:
    """Build the human-facing post-view URL for a given engine."""
    base = (base or "").rstrip("/")
    if engine == "danbooru":
        return f"{base}/posts/{post_id}"
    if engine == "moebooru":
        return f"{base}/post/show/{post_id}"
    # gelbooru-style
    return f"{base}/index.php?page=post&s=view&id={post_id}"


def post_url(site: str, post: dict, custom_url: str = "", api_type: str = "danbooru") -> str | None:
    """The browser URL of `post`'s page on `site`, or None if it can't be built
    (missing id, unknown site, or custom site with no URL)."""
    post_id = post.get("id")
    if post_id is None:
        return None
    if site == "custom":
        if not custom_url:
            return None
        return _post_page(custom_url, api_type, post_id)
    domain = SITE_DOMAINS.get(site)
    if not domain:
        return None
    return _post_page(f"https://{domain}", _SITE_ENGINE.get(site, "gelbooru"), post_id)


# Media categories by file extension.
GIF_EXTS = {"gif"}
VIDEO_EXTS = {"mp4", "webm", "m4v", "mov"}
ANIMATED_EXTS = GIF_EXTS | VIDEO_EXTS  # played, not shown as a still


def url_ext(url: str) -> str:
    """Lower-case file extension of a URL, ignoring any query string."""
    return (url or "").split("?")[0].rsplit(".", 1)[-1].lower()


def media_category(url: str) -> str:
    """'video', 'gif', or 'image' for a media URL."""
    ext = url_ext(url)
    if ext in VIDEO_EXTS:
        return "video"
    if ext in GIF_EXTS:
        return "gif"
    return "image"


def random_media(site: str, tags: str, limit: int = 20, api_key: str = "",
                 user_id: str = "", exclude: str = "", rating: str = "any",
                 images: bool = True, gifs: bool = True, videos: bool = True,
                 custom_url: str = "", api_type: str = "danbooru",
                 sort: str = "") -> dict | None:
    """Pick a random post for `tags`, restricted to the enabled categories
    (still images / GIFs / videos), or None. The returned dict carries file_url
    plus id (for post_url())."""
    allowed = {c for c, on in (("image", images), ("gif", gifs), ("video", videos)) if on}
    # Use positive filetype: filter when a single non-image type is requested
    # so the API only returns matching posts instead of wasting the window.
    if not images:
        if gifs and not videos:
            tags = (tags + " " if tags else "") + "filetype:gif"
        elif videos and not gifs:
            tags = (tags + " " if tags else "") + "filetype:mp4"
        else:
            exclude = (exclude + " " if exclude else "") + "filetype:jpg filetype:png filetype:jpeg filetype:webp filetype:avif"
    if sort == "random":
        limit = max(limit, 200)
    posts = search(site, tags, limit=limit, api_key=api_key, user_id=user_id,
                   exclude=exclude, rating=rating, custom_url=custom_url,
                   api_type=api_type, sort=sort)
    matching = [p for p in posts
                if p.get("file_url") and media_category(p["file_url"]) in allowed]
    if posts and not matching:
        logging.info(f"booru: {len(posts)} result(s) but none matched enabled types {sorted(allowed)}.")
    return random.choice(matching) if matching else None


def random_media_url(site: str, tags: str, limit: int = 20, api_key: str = "",
                     user_id: str = "", exclude: str = "", rating: str = "any",
                     images: bool = True, gifs: bool = True, videos: bool = True,
                     custom_url: str = "", api_type: str = "danbooru",
                     sort: str = "") -> str | None:
    """A random media URL for `tags`, restricted to the enabled categories, or
    None. Thin wrapper over random_media() for callers that only need the URL."""
    post = random_media(site, tags, limit, api_key, user_id, exclude, rating,
                        images, gifs, videos, custom_url, api_type, sort)
    return post.get("file_url") if post else None


def random_image_url(site: str, tags: str, limit: int = 20, api_key: str = "",
                     user_id: str = "", exclude: str = "", rating: str = "any",
                     sort: str = "") -> str | None:
    """Back-compat: a random still-image URL (no animated media)."""
    return random_media_url(site, tags, limit, api_key, user_id, exclude, rating,
                            images=True, gifs=False, videos=False, sort=sort)


def fetch_bytes(url: str, timeout: int = 10) -> bytes:
    import requests
    from urllib.parse import urlparse
    # Many booru image CDNs (e.g. img*.gelbooru.com) hotlink-protect full-size
    # files: a bare request returns an HTML interstitial, not the image. Sending
    # a browser User-Agent + a same-origin Referer returns the real bytes.
    parts = urlparse(url)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"{parts.scheme}://{parts.netloc}/",
    }
    # If we have a PoW-authenticated session for this host, reuse its cookies
    # (some boorus require the anti-bot cookie for image/media URLs too).
    host_key = f"{parts.scheme}://{parts.netloc}"
    sess = None
    with _pow_lock:
        entry = _pow_sessions.get(host_key)
        if entry:
            s, expiry = entry
            if time.time() < expiry - 60:
                sess = s
    if sess:
        response = sess.get(url, headers=headers, timeout=timeout)
    else:
        response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    ctype = response.headers.get("content-type", "?")
    if not ctype.startswith(("image/", "video/")):
        # A non-media type here usually means hotlink protection or an expired
        # URL returned an HTML page; surface it instead of failing opaquely.
        logging.warning(
            f"booru fetch: {parts.netloc} returned {ctype} (not media) for {url} — "
            "likely hotlink-protected or an expired link.")
    return response.content
