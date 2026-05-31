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

# A small, SAFE whitelist of things the AI companion may do in Edgeware, when
# the user has enabled companion control. Two entry points share this registry:
# tag parsing (works with any model) and formal tool-calling.
#
# SAFETY: only non-destructive, bounded actions are exposed here. Nothing that
# deletes/replaces files, fills the drive, blacklists, disables panic or engages
# panic lockout is reachable. Panic always works regardless. Actions are also
# globally rate-limited so the companion can't flood the screen or the toy.

import logging
import re
import time

_COOLDOWN = 3.0  # seconds between any companion-initiated actions
_last_action = 0.0

# name -> (human description, {param: "type desc"} or {})
_SPEC = {
    "popup": ("Spawn an image popup now.", {}),
    "prompt": ("Make the user type out a prompt.", {}),
    "denial": ("Show the user a denial message.", {}),
    "vibrate": ("Pulse the connected toy.", {"intensity": "0-100 strength"}),
    "notify": ("Send the user a short notification in your voice.", {"text": "the message"}),
    "wallpaper": ("Change the desktop wallpaper to another from the pack.", {}),
}

_TAG_RE = re.compile(r"\[do:(\w+)(?:=([^\]]*))?\]", re.IGNORECASE)


def parse_tags(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Pull [do:name] / [do:name=arg] tags out of a reply. Returns the cleaned
    spoken text and the list of (name, arg)."""
    actions = [(m.group(1).lower(), (m.group(2) or "").strip()) for m in _TAG_RE.finditer(text)]
    clean = _TAG_RE.sub("", text).strip()
    return clean, actions


def tool_schemas() -> list[dict]:
    """OpenAI/Ollama-style tool definitions for the whitelist."""
    tools = []
    for name, (desc, params) in _SPEC.items():
        props = {}
        required = []
        for pname, pdesc in params.items():
            ptype = "integer" if pname == "intensity" else "string"
            props[pname] = {"type": ptype, "description": pdesc}
            required.append(pname)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        })
    return tools


def vocabulary() -> str:
    """A compact description of the tags for a system prompt (tag mode)."""
    lines = []
    for name, (desc, params) in _SPEC.items():
        tag = f"[do:{name}={'/'.join(params)}]" if params else f"[do:{name}]"
        lines.append(f"{tag} — {desc}")
    return "\n".join(lines)


def execute(name: str, arg, settings, pack, state) -> None:
    """Run a whitelisted action, bounded and rate-limited. Unknown names are
    ignored. Runs popup/prompt creation on the GTK main thread."""
    global _last_action
    name = (name or "").lower()
    if name not in _SPEC:
        logging.debug(f"companion action '{name}' not in whitelist; ignored")
        return
    now = time.monotonic()
    if now - _last_action < _COOLDOWN:
        return  # rate-limited
    _last_action = now

    from gi.repository import GLib
    arg_str = arg if isinstance(arg, str) else (arg or {})

    try:
        if name == "popup":
            from features.image_popup import ImagePopup
            GLib.idle_add(lambda: (ImagePopup(settings, pack, state), False)[1])
        elif name == "prompt":
            from features.prompt import Prompt
            GLib.idle_add(lambda: (Prompt(settings, pack, state), False)[1])
        elif name == "denial":
            _notify(pack.random_denial(), settings, pack, state)
        elif name == "notify":
            text = arg_str.get("text") if isinstance(arg_str, dict) else str(arg_str)
            _notify((text or pack.random_notification() or "…").strip()[:200], settings, pack, state)
        elif name == "wallpaper":
            _rotate_wallpaper(settings, pack)
        elif name == "vibrate":
            _vibrate(arg_str, settings, state)
    except Exception as e:
        logging.warning(f"companion action '{name}' failed: {e}")


def _notify(message: str, settings, pack, state) -> None:
    if not message:
        return
    from features.companion import resolve_avatar
    from features.misc import notify
    persona = getattr(getattr(state, "companion", None), "persona", None)
    title = getattr(persona, "name", None) or "Companion"
    icon = resolve_avatar(settings, pack, persona)
    notify(title, message, icon=str(icon) if icon else None)


def _rotate_wallpaper(settings, pack) -> None:
    import random
    from os_utils import set_wallpaper
    wallpapers = getattr(settings, "wallpapers", None) or []
    if wallpapers:
        set_wallpaper(pack.paths.root / random.choice(wallpapers))


def _vibrate(arg, settings, state) -> None:
    toy = getattr(state, "sextoy", None)
    if not (toy and getattr(toy, "connected", False)):
        return
    try:
        intensity = int(arg.get("intensity")) if isinstance(arg, dict) else int(arg)
    except (TypeError, ValueError):
        intensity = 60
    intensity = max(0, min(100, intensity))
    # Cap by the device's general force limit (same as event vibrations).
    limit = 100
    try:
        devices = getattr(settings, "sextoys", {}) or {}
        limits = [int(d.get("sextoy_general_vibration_force", 100)) for d in devices.values() if isinstance(d, dict)]
        if limits:
            limit = min(limits)
    except Exception:
        pass
    force = round(min(intensity, limit) / 100.0, 2)
    for idx in list(getattr(toy, "devices", {}) or {}):
        toy.vibrate(idx, force, 1.5)
