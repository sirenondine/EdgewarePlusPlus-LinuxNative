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
        image_b64: str | None = None,
        tools: list | None = None,
        on_tool_calls=None,
    ) -> None:
        """Stream a completion for `messages`. Calls on_token per chunk, then
        on_done(full_text) once, or on_error(exc) on failure. Blocking; run on a
        worker thread. If `stop` is given, it is polled between chunks and a True
        result aborts cleanly (on_done still fires with what arrived so far).
        If `image_b64` is given (base64 JPEG/PNG), it is attached to the last
        user message for vision-capable models."""
        ...


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.model = model
        self.timeout = timeout

    def stream(self, messages, on_token, on_done, on_error, *, stop=None, image_b64=None,
               tools=None, on_tool_calls=None) -> None:
        url = f"{self.base_url}/api/chat"
        payload = {"model": self.model, "messages": _attach_image_ollama(messages, image_b64), "stream": True}
        if tools:
            payload["tools"] = tools
        acc: list[str] = []
        calls: list[tuple[str, dict]] = []
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
                    message = obj.get("message") or {}
                    chunk = message.get("content", "")
                    if chunk:
                        acc.append(chunk)
                        on_token(chunk)
                    for tc in message.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        calls.append((fn.get("name", ""), fn.get("arguments") or {}))
                    if obj.get("done"):
                        break
            if calls and on_tool_calls:
                on_tool_calls(calls)
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

    def stream(self, messages, on_token, on_done, on_error, *, stop=None, image_b64=None,
               tools=None, on_tool_calls=None) -> None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": _attach_image_openai(messages, image_b64), "stream": True}
        if tools:
            payload["tools"] = tools
        acc: list[str] = []
        tool_frags: dict[int, dict] = {}  # index -> {name, args(str)}
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
                    delta = choices[0].get("delta") or {}
                    if delta.get("content"):
                        acc.append(delta["content"])
                        on_token(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        slot = tool_frags.setdefault(tc.get("index", 0), {"name": "", "args": ""})
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["args"] += fn["arguments"]
            if tool_frags and on_tool_calls:
                calls = []
                for slot in tool_frags.values():
                    try:
                        args = json.loads(slot["args"]) if slot["args"] else {}
                    except Exception:
                        args = {}
                    calls.append((slot["name"], args))
                on_tool_calls(calls)
            on_done("".join(acc))
        except Exception as e:
            on_error(e)


class OpenCodeBackend:
    """opencode (opencode.ai) headless server. Uses its native session API — not
    OpenAI-compatible — via the synchronous POST /session/:id/message endpoint
    (no token streaming; the full reply arrives at once). A fresh session is
    created per call so opencode's own history doesn't accumulate / duplicate the
    messages we already pass. `api_key`, if set, is the OPENCODE_SERVER_PASSWORD
    (HTTP basic auth, username 'opencode'). `model` is "providerID/modelID"."""

    name = "opencode"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or "http://localhost:4096").rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _auth(self):
        return ("opencode", self.api_key) if self.api_key else None

    def stream(self, messages, on_token, on_done, on_error, *, stop=None, image_b64=None,
               tools=None, on_tool_calls=None) -> None:
        # Non-streaming: opencode's only stream is a bus-wide SSE feed; the
        # synchronous message endpoint is simpler and fine for our short prompts.
        try:
            auth = self._auth()
            r = requests.post(f"{self.base_url}/session", json={}, auth=auth, timeout=self.timeout)
            r.raise_for_status()
            session_id = r.json().get("id")
            if not session_id:
                raise RuntimeError("opencode: no session id returned")

            system = "\n\n".join(
                m["content"] for m in messages
                if m.get("role") == "system" and isinstance(m.get("content"), str)
            )
            convo = "\n".join(
                m["content"] for m in messages
                if m.get("role") != "system" and isinstance(m.get("content"), str)
            )

            body: dict = {"parts": [{"type": "text", "text": convo}]}
            if system:
                body["system"] = system
            if self.model and "/" in self.model:
                provider_id, model_id = self.model.split("/", 1)
                body["model"] = {"providerID": provider_id, "modelID": model_id}

            r2 = requests.post(f"{self.base_url}/session/{session_id}/message",
                               json=body, auth=auth, timeout=self.timeout)
            r2.raise_for_status()
            data = r2.json()
            parts = data.get("parts", []) if isinstance(data, dict) else []
            text = "".join(
                p.get("text", "") for p in parts
                if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
            if text:
                on_token(text)
            on_done(text)
        except Exception as e:
            on_error(e)


class OpenCodeCLIBackend:
    """opencode via its `run` CLI instead of the HTTP server: shells out to
    `opencode run -m <model> <prompt>` and returns stdout. No streaming — the
    whole reply arrives at once. base_url, if set, is passed as --attach to reuse
    a running `opencode serve` (faster than cold-starting each call)."""

    name = "opencode-cli"

    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None,
                 timeout: int = DEFAULT_TIMEOUT, binary: str = "opencode") -> None:
        self.model = model
        self.attach = (base_url or "").strip()
        self.api_key = api_key
        self.timeout = timeout
        self.binary = binary

    def stream(self, messages, on_token, on_done, on_error, *, stop=None, image_b64=None,
               tools=None, on_tool_calls=None) -> None:
        import subprocess

        system = "\n\n".join(
            m["content"] for m in messages
            if m.get("role") == "system" and isinstance(m.get("content"), str)
        )
        convo = "\n".join(
            m["content"] for m in messages
            if m.get("role") != "system" and isinstance(m.get("content"), str)
        )
        prompt = f"{system}\n\n{convo}".strip() if system else convo

        cmd = [self.binary, "run"]
        if self.model and "/" in self.model:
            cmd += ["-m", self.model]
        if self.attach:
            cmd += ["--attach", self.attach]
        if self.api_key:
            cmd += ["-p", self.api_key]
        cmd.append(prompt)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"opencode exited {proc.returncode}")
            text = proc.stdout.strip()
            if text:
                on_token(text)
            on_done(text)
        except FileNotFoundError:
            on_error(RuntimeError(f"'{self.binary}' not found on PATH"))
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

    def stream(self, messages, on_token, on_done, on_error, *, stop=None, image_b64=None,
               tools=None, on_tool_calls=None) -> None:
        try:
            line = self._line()
            if line:
                on_token(line)
            on_done(line)
        except Exception as e:
            on_error(e)


def _attach_image_ollama(messages: list[Message], image_b64: str | None) -> list[Message]:
    """Attach a base64 image to the last user message, Ollama style (an
    `images` list of bare base64 strings)."""
    if not image_b64:
        return messages
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            m["images"] = [image_b64]
            break
    return out


def _attach_image_openai(messages: list[Message], image_b64: str | None) -> list[Message]:
    """Attach a base64 image to the last user message, OpenAI style (a content
    array with an image_url data URI)."""
    if not image_b64:
        return messages
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = [
                {"type": "text", "text": m.get("content", "")},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ]
            break
    return out


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
    if kind == "opencode":
        return OpenCodeBackend(base_url, model or "", api_key, timeout)
    if kind == "opencode-cli":
        return OpenCodeCLIBackend(model or "", base_url, api_key, timeout)
    if kind != "scripted":
        logging.warning(f"Unknown companion backend '{backend}', using scripted fallback.")
    return ScriptedBackend(scripted_corpus)
