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

"""Pack content editor backend.

Operates on the *raw* JSON of a pack's index.json / info.json — load, mutate,
atomic-write — rather than round-tripping through pack.load's dataclasses, which
normalise and drop unknown keys (media maps, ALLOW_EXTRA fields). Edits here must
therefore preserve everything the editor doesn't touch.

Writes are validated against a focused schema first and written atomically
(temp file + os.replace) so a torn file can never land on disk.
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from voluptuous import ALLOW_EXTRA, All, Optional, Range, Schema
from voluptuous.error import Invalid

# default-mood fields the Phase 1 editor exposes, by their index.json key.
DEFAULT_TEXT_LISTS = ["captions", "denial", "subliminals", "notifications", "prompts"]
DEFAULT_STRINGS = {
    "popupClose": "I Submit <3",
    "promptCommand": "Type for me, slut~",
    "promptSubmit": "I Submit <3",
}
INFO_FIELDS = ["name", "creator", "version", "description"]

_INDEX_DEFAULT_SCHEMA = Schema(
    {
        Optional("captions"): [str],
        Optional("denial"): [str],
        Optional("subliminals"): [str],
        Optional("notifications"): [str],
        Optional("prompts"): [str],
        Optional("popupClose"): str,
        Optional("promptCommand"): str,
        Optional("promptSubmit"): str,
        Optional("promptMinLength"): All(int, Range(min=1)),
        Optional("promptMaxLength"): All(int, Range(min=1)),
    },
    extra=ALLOW_EXTRA,
)
_INFO_SCHEMA = Schema(
    {"name": str, "id": str, "creator": str, "version": str, "description": str},
    required=True,
    extra=ALLOW_EXTRA,
)


def is_writable(pack_dir: Path) -> bool:
    """True if the pack directory exists and we can write files into it."""
    return pack_dir.is_dir() and os.access(pack_dir, os.W_OK)


def _slugify(name: str) -> str:
    """A safe-ish id from a pack name (alnum, collapsed); falls back to 'pack'."""
    out = "".join(c if c.isalnum() else "" for c in name)
    return out or "pack"


def _read_raw(path: Path) -> dict:
    """Parsed JSON object at `path`, or {} if missing/unreadable/not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"pack edit: could not read {path.name}: {e}")
        return {}


def _write_atomic(path: Path, data: dict) -> None:
    """Write `data` as pretty JSON atomically (temp in the same dir + os.replace)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_atomic_text(path: Path, content: str) -> None:
    """Atomically write plain-text (non-JSON) content."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Asset filename mapping: key → list of candidate filenames (first is canonical dest).
_ASSET_CANDIDATES: dict[str, list[str]] = {
    "icon":     ["icon.ico"],
    "wallpaper":["wallpaper.png"],
    "splash":   ["loading_splash.png", "loading_splash.gif", "loading_splash.jpg",
                 "loading_splash.jpeg", "loading_splash.bmp"],
}

def _web_for(web: dict, mood_name: str, out: dict) -> None:
    """Extract web entries for `mood_name` from a legacy web.json dict and
    append them to `out` as index.json-format `web`/`webArgs` keys."""
    urls = web.get("urls", [])
    args = web.get("args", [])
    moods = web.get("moods", [None] * len(urls))
    matched_urls: list[str] = []
    matched_args: list[list[str]] = []
    for i, url in enumerate(urls):
        m = moods[i] if i < len(moods) else None
        target = "default" if (m is None or m == "default") else m
        if target == mood_name:
            raw_arg = args[i] if i < len(args) else ""
            matched_urls.append(url)
            matched_args.append(raw_arg.split(",") if raw_arg else [""])
    if matched_urls:
        out["web"] = matched_urls
        out["webArgs"] = matched_args


DISCORD_IMAGE_IDS = [
    "furcock_img", "blacked_img", "censored_img", "goon_img", "goon2_img",
    "hypno_img", "futa_img", "healslut_img", "gross_img",
]

# Config keys never written into a pack's config.json (machine- or safety-
# specific — they must not travel between machines inside a pack).
_PACK_CONFIG_BLOCKLIST = {
    "version", "versionplusplus", "packPath", "wallpaperDat",
    "safeword", "panicButton", "globalPanicButton", "drivePath", "safeMode",
    "toggleInternet", "intifaceAddress",
    # Secrets / machine-local endpoints — never ship these in a pack config.
    "companionApiKey", "openaiKey", "opencodeKey",
    "companionBaseUrl", "ollamaUrl", "openaiUrl", "opencodeUrl", "migratedBackendsV2",
}


def create_pack(parent_dir: Path, name: str, creator: str = "Anonymous") -> tuple[Path | None, str | None]:
    """Scaffold a new empty pack under `parent_dir`. Creates the media dirs and a
    minimal info.json + index.json (default mood + one starter mood). Returns
    (pack_dir, None) on success or (None, error)."""
    name = name.strip()
    if not name:
        return None, "Pack name cannot be blank."
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
    if not safe:
        return None, "Pack name has no usable characters."
    pack_dir = parent_dir / safe
    if pack_dir.exists():
        return None, f"A pack folder named \"{safe}\" already exists."
    try:
        for sub in ("img", "vid", "aud", "hypno"):
            (pack_dir / sub).mkdir(parents=True, exist_ok=True)
        _write_atomic(pack_dir / "info.json", {
            "name": name,
            "id": _slugify(name),
            "creator": creator or "Anonymous",
            "version": "1.0",
            "description": "",
        })
        _write_atomic(pack_dir / "index.json", {
            "default": {
                "captions": [],
                "denial": [],
                "subliminals": [],
                "notifications": [],
                "prompts": [],
            },
            "moods": [{"mood": "default", "media": []}],
        })
        return pack_dir, None
    except Exception as e:
        logging.warning(f"pack edit: create_pack failed: {e}")
        return None, str(e)


class PackEditor:
    """In-memory editable view of one pack's index.json + info.json.

    Setters mutate the raw dicts; save_index()/save_info() validate then write.
    The UI layer debounces the saves.
    """

    def __init__(self, pack_dir: Path) -> None:
        self.pack_dir = pack_dir
        self.index_path = pack_dir / "index.json"
        self.info_path = pack_dir / "info.json"
        self.index = _read_raw(self.index_path)
        self.info = _read_raw(self.info_path)

    # --- index.json (default mood) ---------------------------------------
    @property
    def has_index(self) -> bool:
        """Whether this pack ships a modern index.json. Legacy packs (captions.json
        etc.) return False; the editor disables text editing for them in Phase 1
        rather than risk overriding the fallback content with a partial index."""
        return self.index_path.is_file()

    def _default(self) -> dict:
        return self.index.setdefault("default", {})

    def get_list(self, key: str) -> list[str]:
        value = self._default().get(key, [])
        return [str(v) for v in value] if isinstance(value, list) else []

    def set_list(self, key: str, values: list[str]) -> None:
        self._default()[key] = list(values)

    def get_string(self, key: str) -> str:
        return str(self._default().get(key, DEFAULT_STRINGS.get(key, "")))

    def set_string(self, key: str, value: str) -> None:
        self._default()[key] = value

    def get_int(self, key: str, fallback: int = 1) -> int:
        try:
            return int(self._default().get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    def set_int(self, key: str, value: int) -> None:
        self._default()[key] = int(value)

    def validate_index(self) -> str | None:
        """Return an error message if the pending index.json is invalid, else None."""
        try:
            _INDEX_DEFAULT_SCHEMA(self._default())
        except Invalid as e:
            return str(e)
        lo = self.get_int("promptMinLength", 1)
        hi = self.get_int("promptMaxLength", 1)
        if "promptMaxLength" in self._default() and hi < lo:
            return "Prompt max length must be greater than or equal to min length."
        return None

    def save_index(self) -> str | None:
        """Validate + atomically write index.json. Returns an error message on
        failure (and leaves the file untouched), else None."""
        error = self.validate_index()
        if error:
            logging.warning(f"pack edit: refusing to save invalid index.json: {error}")
            return error
        try:
            _write_atomic(self.index_path, self.index)
        except Exception as e:
            logging.warning(f"pack edit: failed to write index.json: {e}")
            return str(e)
        return None

    # --- info.json --------------------------------------------------------
    def get_info(self, field: str) -> str:
        return str(self.info.get(field, ""))

    def set_info(self, field: str, value: str) -> None:
        self.info[field] = value

    def _ensure_info_required(self) -> None:
        """Backfill required info.json fields so a sparse/new file validates."""
        self.info.setdefault("name", self.pack_dir.name)
        self.info.setdefault("id", _slugify(self.info.get("name", self.pack_dir.name)))
        self.info.setdefault("creator", "Anonymous")
        self.info.setdefault("version", "1.0")
        self.info.setdefault("description", "")

    def validate_info(self) -> str | None:
        self._ensure_info_required()
        try:
            _INFO_SCHEMA(self.info)
        except Invalid as e:
            return str(e)
        return None

    def save_info(self) -> str | None:
        error = self.validate_info()
        if error:
            logging.warning(f"pack edit: refusing to save invalid info.json: {error}")
            return error
        try:
            _write_atomic(self.info_path, self.info)
        except Exception as e:
            logging.warning(f"pack edit: failed to write info.json: {e}")
            return str(e)
        return None

    # --- index.json (moods) -----------------------------------------------
    def _moods(self) -> list[dict]:
        return self.index.setdefault("moods", [])

    def _find_mood(self, name: str) -> dict | None:
        return next((m for m in self._moods() if m.get("mood") == name), None)

    def mood_names(self) -> list[str]:
        return [m["mood"] for m in self._moods() if "mood" in m]

    def add_mood(self, name: str) -> str | None:
        """Add a new empty mood. Returns error string if name is blank or duplicate."""
        name = name.strip()
        if not name:
            return "Mood name cannot be blank."
        if name in self.mood_names():
            return f"A mood named \"{name}\" already exists."
        self._moods().append({"mood": name, "media": []})
        return None

    def rename_mood(self, old: str, new: str) -> str | None:
        new = new.strip()
        if not new:
            return "Mood name cannot be blank."
        if new == old:
            return None
        if new in self.mood_names():
            return f"A mood named \"{new}\" already exists."
        mood = self._find_mood(old)
        if mood is None:
            return f"Mood \"{old}\" not found."
        mood["mood"] = new
        # Update the media_moods inverse map (derived at load time but we keep
        # it in sync so media assignment in Phase 2C stays consistent).
        mm = self.index.get("media_moods", {})
        for k, v in mm.items():
            if v == old:
                mm[k] = new
        return None

    def remove_mood(self, name: str) -> None:
        """Remove a mood and clear its media assignments (files become unassigned)."""
        self.index["moods"] = [m for m in self._moods() if m.get("mood") != name]
        mm = self.index.get("media_moods", {})
        keys_to_clear = [k for k, v in mm.items() if v == name]
        for k in keys_to_clear:
            del mm[k]

    # --- per-mood text lists -----------------------------------------------
    def get_mood_list(self, mood_name: str, key: str) -> list[str]:
        mood = self._find_mood(mood_name)
        if mood is None:
            return []
        val = mood.get(key, [])
        return [str(v) for v in val] if isinstance(val, list) else []

    def set_mood_list(self, mood_name: str, key: str, values: list[str]) -> None:
        mood = self._find_mood(mood_name)
        if mood is not None:
            mood[key] = list(values)

    def get_mood_string(self, mood_name: str, key: str) -> str:
        mood = self._find_mood(mood_name)
        return str(mood.get(key, "")) if mood else ""

    def set_mood_string(self, mood_name: str, key: str, value: str) -> None:
        mood = self._find_mood(mood_name)
        if mood is not None:
            mood[key] = value

    # --- index.json (media assignment) -----------------------------------
    def get_media_assignment(self, filename: str) -> str | None:
        """Mood name the file belongs to, or None (unassigned = shows in all moods)."""
        for mood in self._moods():
            if filename in mood.get("media", []):
                return mood.get("mood")
        return None

    def set_media_assignment(self, filename: str, mood_name: str | None) -> None:
        """Assign file to a mood, or unassign (None). Removes from all moods first."""
        for mood in self._moods():
            media = mood.get("media", [])
            if filename in media:
                media.remove(filename)
        if mood_name is not None:
            target = self._find_mood(mood_name)
            if target is not None:
                target.setdefault("media", []).append(filename)

    # --- media files (add / remove) ---------------------------------------
    _MEDIA_DIRS = {"image": "img", "video": "vid", "audio": "aud"}

    def import_media(self, media_type: str, sources: list) -> tuple[list[str], list[str]]:
        """Copy `sources` into the pack's media dir for `media_type`
        (image/video/audio). Returns (copied_filenames, errors). De-dupes names
        by suffixing -1, -2, ... when a file already exists."""
        sub = self._MEDIA_DIRS.get(media_type)
        if not sub:
            return [], [f"Unknown media type: {media_type}"]
        dest_dir = self.pack_dir / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied, errors = [], []
        for src in sources:
            src = Path(src)
            name = src.name
            target = dest_dir / name
            n = 1
            while target.exists():
                target = dest_dir / f"{src.stem}-{n}{src.suffix}"
                n += 1
            try:
                shutil.copy2(src, target)
                copied.append(target.name)
            except Exception as e:
                errors.append(f"{name}: {e}")
        return copied, errors

    def import_root_file(self, src: Path) -> tuple[str | None, str | None]:
        """Copy `src` into the pack root (for companion avatar / spritesheet, which
        are referenced by bare filename relative to the pack). De-dupes the name.
        Returns (filename, None) or (None, error)."""
        src = Path(src)
        target = self.pack_dir / src.name
        n = 1
        while target.exists() and target.resolve() != src.resolve():
            target = self.pack_dir / f"{src.stem}-{n}{src.suffix}"
            n += 1
        try:
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            return target.name, None
        except Exception as e:
            return None, str(e)

    def delete_media(self, media_type: str, filename: str) -> str | None:
        """Delete a media file from disk and drop it from every mood's media
        list. Caller should save_index() after. Returns error or None."""
        sub = self._MEDIA_DIRS.get(media_type)
        if not sub:
            return f"Unknown media type: {media_type}"
        self.set_media_assignment(filename, None)
        path = self.pack_dir / sub / filename
        try:
            if path.is_file():
                path.unlink()
            return None
        except Exception as e:
            return str(e)

    def get_mood_int(self, mood_name: str, key: str, fallback: int = 1) -> int:
        mood = self._find_mood(mood_name)
        if mood is None:
            return fallback
        try:
            return int(mood.get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    def set_mood_int(self, mood_name: str, key: str, value: int) -> None:
        mood = self._find_mood(mood_name)
        if mood is not None:
            mood[key] = int(value)

    # --- Phase 3: assets (icon / wallpaper / splash) ----------------------
    def get_asset_path(self, key: str) -> Path | None:
        """Current on-disk path for the asset, or None if not present."""
        for name in _ASSET_CANDIDATES.get(key, []):
            p = self.pack_dir / name
            if p.is_file():
                return p
        return None

    def set_asset(self, key: str, src: Path) -> str | None:
        """Copy `src` into the pack dir as the canonical asset file.
        Clears any existing files for that key first (handles splash extension changes).
        Returns an error string on failure, else None."""
        for name in _ASSET_CANDIDATES.get(key, []):
            old = self.pack_dir / name
            if old.is_file():
                try:
                    old.unlink()
                except OSError:
                    pass
        # Destination: always use the first candidate name, preserving the
        # source extension for splash (which supports multiple extensions).
        candidates = _ASSET_CANDIDATES.get(key, [])
        if key == "splash":
            dest_name = f"loading_splash{src.suffix.lower()}"
        else:
            dest_name = candidates[0] if candidates else src.name
        try:
            shutil.copy2(src, self.pack_dir / dest_name)
            return None
        except Exception as e:
            logging.warning(f"pack edit: failed to set asset {key}: {e}")
            return str(e)

    def clear_asset(self, key: str) -> None:
        for name in _ASSET_CANDIDATES.get(key, []):
            p = self.pack_dir / name
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    # --- Phase 3: discord.dat ---------------------------------------------
    def get_discord(self) -> tuple[str, str]:
        """Returns (status_text, image_id). Empty strings if file missing."""
        try:
            lines = (self.pack_dir / "discord.dat").read_text(encoding="utf-8").splitlines()
            return (lines[0] if lines else ""), (lines[1] if len(lines) > 1 else "")
        except FileNotFoundError:
            return "", ""
        except Exception as e:
            logging.warning(f"pack edit: could not read discord.dat: {e}")
            return "", ""

    def save_discord(self, text: str, image_id: str) -> str | None:
        content = f"{text}\n{image_id}" if image_id else text
        try:
            _write_atomic_text(self.pack_dir / "discord.dat", content)
            return None
        except Exception as e:
            logging.warning(f"pack edit: failed to write discord.dat: {e}")
            return str(e)

    def clear_discord(self) -> None:
        p = self.pack_dir / "discord.dat"
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    # --- Phase 3: companion.json ------------------------------------------
    def get_companion(self) -> dict:
        """Raw companion.json dict, or {} if not present."""
        return _read_raw(self.pack_dir / "companion.json")

    def save_companion(self, data: dict) -> str | None:
        try:
            _write_atomic(self.pack_dir / "companion.json", data)
            return None
        except Exception as e:
            logging.warning(f"pack edit: failed to write companion.json: {e}")
            return str(e)

    def clear_companion(self) -> None:
        p = self.pack_dir / "companion.json"
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    # --- Phase 4: save current settings as pack config.json ---------------
    def save_config_from(self, full_config: dict) -> str | None:
        """Write `full_config` (the user's live config) into the pack as
        config.json, minus machine/safety-specific keys. Returns error or None."""
        filtered = {
            k: v for k, v in full_config.items()
            if k not in _PACK_CONFIG_BLOCKLIST
        }
        try:
            _write_atomic(self.pack_dir / "config.json", filtered)
            return None
        except Exception as e:
            logging.warning(f"pack edit: failed to write config.json: {e}")
            return str(e)

    def config_key_count(self) -> int:
        return len(_read_raw(self.pack_dir / "config.json"))

    # --- Phase 4: corruption.json -----------------------------------------
    def get_corruption(self) -> dict:
        """Raw corruption.json, normalised to have moods/wallpapers/config/names dicts."""
        data = _read_raw(self.pack_dir / "corruption.json")
        data.setdefault("moods", {})
        data.setdefault("wallpapers", {})
        data.setdefault("config", {})
        data.setdefault("names", {})
        return data

    def corruption_level_count(self) -> int:
        data = self.get_corruption()
        wp = data["wallpapers"]
        return max(
            [int(k) for k in data["moods"] if k.isdigit()]
            + [int(k) for k in data["config"] if k.isdigit()]
            + [int(k) for k in wp if k.isdigit()]
            + [int(k) for k in data["names"] if k.isdigit()]
            + [0]
        )

    def save_corruption(self, data: dict) -> str | None:
        # Drop fully-empty levels to keep the file tidy.
        try:
            _write_atomic(self.pack_dir / "corruption.json", data)
            return None
        except Exception as e:
            logging.warning(f"pack edit: failed to write corruption.json: {e}")
            return str(e)

    # --- Legacy migration -------------------------------------------------
    @property
    def has_legacy(self) -> bool:
        """True if pack has old-format files and no index.json yet."""
        return not self.has_index and any(
            (self.pack_dir / f).is_file()
            for f in ("captions.json", "media.json", "prompt.json", "web.json")
        )

    def migrate_legacy_to_index(self) -> str | None:
        """Convert legacy captions/media/prompt/web.json to a modern index.json.
        Non-destructive — legacy files are left in place.
        Returns an error string on failure, else None."""
        from paths import PackPaths
        from pack.load import load_captions, load_media, load_prompts, load_web

        if self.has_index:
            return "Pack already has index.json."

        paths = PackPaths(self.pack_dir)

        # Load all legacy files (try_load handles encoding quirks).
        captions = load_captions(paths)   # dict with "prefix", "default", mood keys…
        media_inv = load_media(paths)     # {filename: mood_name} (default excluded)
        prompts = load_prompts(paths)     # dict with "moods", "default", mood keys…
        web = load_web(paths)             # {"urls": [...], "args": [...], "moods": [...]}

        # ---- Collect all mood names (stable order, deduplicated) ----------
        seen: dict[str, None] = {}
        for source in [
            captions.get("prefix", []),
            list({v for v in media_inv.values()}),
            prompts.get("moods", []),
            [m for m in web.get("moods", []) if m and m != "default"],
        ]:
            for m in source:
                if m and m != "default":
                    seen[m] = None
        mood_names = list(seen)

        # ---- Invert media map: mood → [filenames] ------------------------
        mood_media: dict[str, list[str]] = {m: [] for m in mood_names}
        for filename, mood_name in media_inv.items():
            if mood_name in mood_media:
                mood_media[mood_name].append(filename)

        # ---- Build default section ----------------------------------------
        default: dict = {}
        if captions.get("default"):
            default["captions"] = captions["default"]
        if captions.get("denial"):
            default["denial"] = captions["denial"]
        if captions.get("subliminals"):
            default["subliminals"] = captions["subliminals"]
        if captions.get("notifications"):
            default["notifications"] = captions["notifications"]
        if captions.get("subtext"):
            default["popupClose"] = captions["subtext"]
        if prompts.get("default"):
            default["prompts"] = prompts["default"]
        if prompts.get("commandtext"):
            default["promptCommand"] = prompts["commandtext"]
        if prompts.get("subtext"):
            default["promptSubmit"] = prompts["subtext"]
        if prompts.get("minLen"):
            default["promptMinLength"] = prompts["minLen"]
        if prompts.get("maxLen"):
            default["promptMaxLength"] = prompts["maxLen"]

        # Web links for default (mood == None or "default")
        _web_for(web, "default", default)

        # ---- Build moods list --------------------------------------------
        moods_out: list[dict] = []
        for mood_name in mood_names:
            entry: dict = {"mood": mood_name, "media": mood_media.get(mood_name, [])}
            # Mood-specific captions
            if mood_name in captions:
                entry["captions"] = captions[mood_name]
            # Max clicks from prefix_settings
            ps = captions.get("prefix_settings", {}).get(mood_name, {})
            if ps.get("max"):
                entry["maxClicks"] = ps["max"]
            # Mood-specific prompts
            if mood_name in prompts:
                entry["prompts"] = prompts[mood_name]
            # Mood-specific web
            _web_for(web, mood_name, entry)
            moods_out.append(entry)

        # ---- Write -------------------------------------------------------
        try:
            _write_atomic(self.index_path, {"default": default, "moods": moods_out})
            # Refresh our in-memory view so has_index becomes True immediately.
            self.index = _read_raw(self.index_path)
            return None
        except Exception as e:
            logging.warning(f"pack edit: legacy migration failed: {e}")
            return str(e)
