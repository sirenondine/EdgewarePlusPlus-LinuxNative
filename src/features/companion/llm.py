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

# Pluggable LLM backends for the AI companion. Bring-your-own inference:
#   - OllamaBackend       local Ollama server (default; nothing leaves the box)
#   - OpenAIBackend       any OpenAI-compatible endpoint (OpenAI, OpenRouter,
#                         LM Studio, llama.cpp/koboldcpp/vLLM servers, ...)
#   - ScriptedBackend     no network at all; replays pack-supplied lines
#
# This module is deliberately GUI- and pack-agnostic: it only knows messages
# (OpenAI chat shape: [{"role","content"}, ...]) and string tokens. stream() is
# blocking and meant to be called from a worker thread; it pushes tokens through
# callbacks as they arrive. Keep GTK and Pack out of here.

import json
import logging
import random
from typing import Callable, Iterable, Protocol, runtime_checkable

import requests

# Generous: local models can take seconds to first token, especially cold.
DEFAULT_TIMEOUT = 60

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}
OnToken = Callable[[str], None]
OnDone = Callable[[str], None]
OnError = Callable[[Exception], None]
Stop = Callable[[], bool]  # return True to abort streaming early


@runtime_checkable
class LLMBackend(Protocol):
    name: str

    def stream(
        self,
        messages: list[Message],
        on_token: OnToken,
        on_done: OnDone,
        on_error: OnError,
        *,
        stop: Stop | None = None,
    ) -> None:
        """Stream a completion for `messages`. Calls on_token per chunk, then
        on_done(full_text) once, or on_error(exc) on failure. Blocking; run on a
        worker thread. If `stop` is given, it is polled between chunks and a True
        result aborts cleanly (on_done still fires with what arrived so far)."""
        ...


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.model = model
        self.timeout = timeout

    def stream(self, messages, on_token, on_done, on_error, *, stop=None) -> None:
        url = f"{self.base_url}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": True}
        acc: list[str] = []
        try:
            with requests.post(url, json=payload, stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if stop and stop():
                        break
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        raise RuntimeError(obj["error"])
                    chunk = (obj.get("message") or {}).get("content", "")
                    if chunk:
                        acc.append(chunk)
                        on_token(chunk)
                    if obj.get("done"):
                        break
            on_done("".join(acc))
        except Exception as e:
            on_error(e)


class OpenAIBackend:
    name = "openai"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _endpoint(self) -> str:
        # Accept either ".../v1" or a bare host; normalise to the chat route.
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def stream(self, messages, on_token, on_done, on_error, *, stop=None) -> None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": messages, "stream": True}
        acc: list[str] = []
        try:
            with requests.post(self._endpoint(), json=payload, headers=headers, stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if stop and stop():
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content", "")
                    if delta:
                        acc.append(delta)
                        on_token(delta)
            on_done("".join(acc))
        except Exception as e:
            on_error(e)


class ScriptedBackend:
    """No-network fallback: emits a single pack-supplied line. `corpus` is either
    a callable returning a line (e.g. pack.random_caption) or an iterable of
    lines to choose from. The whole line arrives as one token."""

    name = "scripted"

    def __init__(self, corpus: Callable[[], str | None] | Iterable[str] | None) -> None:
        self._corpus = corpus

    def _line(self) -> str:
        if callable(self._corpus):
            return self._corpus() or ""
        lines = list(self._corpus or [])
        return random.choice(lines) if lines else ""

    def stream(self, messages, on_token, on_done, on_error, *, stop=None) -> None:
        try:
            line = self._line()
            if line:
                on_token(line)
            on_done(line)
        except Exception as e:
            on_error(e)


def make_backend(
    backend: str | None,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    scripted_corpus: Callable[[], str | None] | Iterable[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> LLMBackend:
    """Build a backend from config. Unknown / empty backend -> scripted, so the
    companion always has a working (if dumb) voice even with nothing installed."""
    kind = (backend or "scripted").lower()
    if kind == "ollama":
        return OllamaBackend(base_url, model or "", timeout)
    if kind == "openai":
        return OpenAIBackend(base_url, model or "", api_key, timeout)
    if kind != "scripted":
        logging.warning(f"Unknown companion backend '{backend}', using scripted fallback.")
    return ScriptedBackend(scripted_corpus)
