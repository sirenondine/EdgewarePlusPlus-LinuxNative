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

# Companion engine: turns triggers (greeting, idle, popup events, ...) into
# spoken lines via a pluggable LLM backend (see llm.py). GUI-agnostic — it takes
# plain on_start/on_token/on_done/on_error callbacks; the window wraps them in
# GLib.idle_add. Each utterance streams on its own worker thread; only one runs
# at a time (a new request while busy is dropped, so the companion never piles
# up or overlaps itself). History is bounded and in-memory only (nothing is
# written to disk — also the privacy-safe choice).

import logging
import random
import threading
from collections import deque

from features.companion import llm
from pack.data import Persona

_HISTORY_TURNS = 6  # user+assistant pairs kept as context

# Used when a pack ships no companion.json but the user enables the companion.
_DEFAULT_SYSTEM = (
    "You are a flirtatious, teasing companion living on the user's desktop. "
    "Stay fully in character. Keep every reply to one or two short sentences. "
    "Be playful, suggestive and a little bossy. Never mention being an AI or a "
    "language model, and never break character."
)
_DEFAULT_PERSONA = Persona(
    name="Companion",
    system_prompt=_DEFAULT_SYSTEM,
    greetings=["Hey you.", "Back for more?", "There you are."],
    idle_lines=["Eyes on the screen.", "Good pet.", "Don't stop now.", "I'm watching."],
)


class Companion:
    def __init__(self, settings, pack, *, on_start, on_token, on_done, on_error=None) -> None:
        self.settings = settings
        self.pack = pack
        self.persona = self._resolve_persona()
        self._on_start = on_start
        self._on_token = on_token
        self._on_done = on_done
        self._on_error = on_error or (lambda e: logging.warning(f"Companion backend error: {e}"))

        self._history: deque = deque(maxlen=2 * _HISTORY_TURNS)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._busy = False
        self.backend = self._build_backend()
        logging.info(f"Companion ready: persona='{self.persona.name}' backend={self.backend.name}")

    def _resolve_persona(self) -> Persona:
        """Persona precedence: config overrides (name / system prompt from the
        config window) layered over the pack's companion.json, else the built-in
        default. Greetings/idle lines (the scripted fallback corpus) come from
        the pack/default."""
        base = self.pack.companion or _DEFAULT_PERSONA
        name = (getattr(self.settings, "companion_name", "") or "").strip() or base.name
        prompt = (getattr(self.settings, "companion_system_prompt", "") or "").strip() or base.system_prompt
        if name == base.name and prompt == base.system_prompt:
            return base
        return Persona(
            name=name, avatar=base.avatar, spritesheet=base.spritesheet,
            system_prompt=prompt, greetings=base.greetings, idle_lines=base.idle_lines)

    # ------------------------------------------------------------------
    def _build_backend(self) -> llm.LLMBackend:
        s = self.settings
        # Scripted fallback corpus: persona lines first, else live pack captions.
        corpus = self.persona.idle_lines or self.persona.greetings or None
        return llm.make_backend(
            getattr(s, "companion_backend", "scripted"),
            base_url=getattr(s, "companion_base_url", None),
            model=getattr(s, "companion_model", None),
            api_key=(getattr(s, "companion_api_key", None) or None),
            scripted_corpus=corpus or (lambda: self.pack.random_caption()),
        )

    def _messages(self, user_text: str) -> list[dict]:
        system = self.persona.system_prompt or _DEFAULT_SYSTEM
        messages = [{"role": "system", "content": system}]
        context = self._context_block()
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def _context_block(self) -> str:
        """Background facts that give the companion insight into the user and
        the current pack. Rebuilt each turn (cheap) so live values like the
        gamification level stay current."""
        lines: list[str] = []

        info = getattr(self.pack, "info", None)
        if info:
            desc = (getattr(info, "description", "") or "").strip()
            if desc and desc != "No description set.":
                lines.append(f"Pack theme: \"{info.name}\" — {desc}")

        # Where this pack sends the user (domains only, not full URLs).
        try:
            from urllib.parse import urlparse
            domains = sorted({urlparse(w.url).netloc for w in self.pack.find_list("web") if getattr(w, "url", "")})
            if domains:
                lines.append("The user gets sent to sites like: " + ", ".join(domains[:8]))
        except Exception:
            pass

        memory = (getattr(self.settings, "companion_memory", "") or "").strip()
        if memory:
            lines.append(f"What you know about the user: {memory}")

        try:
            if getattr(self.settings, "gamification", False):
                from features import gamification
                lines.append(f"The user is at progression level {gamification.progress().level}.")
        except Exception:
            pass

        if not lines:
            return ""
        return "Background for flavour (do not recite verbatim):\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    def say(self, user_text: str, image_b64: str | None = None) -> None:
        """Stream one utterance. Dropped if an utterance is already in flight."""
        if self._busy:
            return
        threading.Thread(target=self._run, args=(user_text, image_b64), daemon=True).start()

    def _run(self, user_text: str, image_b64: str | None = None) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True
        self._cancel.clear()
        acc = {"text": ""}

        def tok(t: str) -> None:
            acc["text"] += t
            self._on_token(t)

        def done(full: str) -> None:
            text = (full or acc["text"]).strip()
            if text:
                # Store only the text in history, never the image.
                self._history.append({"role": "user", "content": user_text})
                self._history.append({"role": "assistant", "content": text})
            self._busy = False
            self._on_done(text)

        def err(e: Exception) -> None:
            self._busy = False
            self._on_error(e)

        self._on_start()
        self.backend.stream(self._messages(user_text), tok, done, err,
                            stop=self._cancel.is_set, image_b64=image_b64)

    def observe(self) -> None:
        """Capture the screen and react to what's on it via a vision model.
        No-op if busy or capture is unavailable. The screenshot is sent to the
        backend but never kept in history."""
        if self._busy:
            return
        threading.Thread(target=self._run_observe, daemon=True).start()

    def _run_observe(self) -> None:
        from features.companion import vision
        image_b64 = vision.capture_screenshot()
        if not image_b64:
            return
        self._run("(screen) React in one short in-character line to what is on the user's screen right now.",
                  image_b64=image_b64)

    # ------------------------------------------------------------------
    # Convenience triggers
    def greet(self) -> None:
        hint = random.choice(self.persona.greetings) if self.persona.greetings else None
        self.say(f"(greeting) Greet your pet in one short line, in the spirit of: {hint}" if hint
                 else "(greeting) Greet your pet in one short line.")

    def idle_chatter(self) -> None:
        hint = random.choice(self.persona.idle_lines) if self.persona.idle_lines else None
        self.say(f"(idle) Say a short spontaneous line, riffing on: {hint}" if hint
                 else "(idle) Say a short spontaneous teasing line.")

    def react(self, event: str, detail: str = "", image_path: str | None = None) -> None:
        """React to an app event (e.g. popup_open, denial). If image_path is
        given, the image (e.g. the popup itself) is encoded on a worker thread
        and shown to the vision model."""
        ctx = f"(event:{event}) {detail}".strip()
        text = f"{ctx}\nRespond in one short in-character line."
        if image_path:
            if self._busy:
                return
            threading.Thread(target=self._react_image, args=(text, image_path), daemon=True).start()
        else:
            self.say(text)

    def _react_image(self, text: str, image_path: str) -> None:
        from features.companion import vision
        self._run(text, image_b64=vision.encode_image_file(image_path))

    def cancel(self) -> None:
        self._cancel.set()
