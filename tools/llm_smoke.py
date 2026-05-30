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

# Throwaway harness to exercise the companion LLM backends before any UI exists.
# Streams a completion and prints tokens as they arrive.
#
#   python tools/llm_smoke.py \
#       --backend ollama --base http://192.168.1.179:11434 \
#       --model huihui_ai/gemma-4-abliterated:e4b \
#       --system "You are a teasing companion." --prompt "Say hi in one sentence."
#
#   python tools/llm_smoke.py --backend scripted   # no network

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from features.companion.llm import make_backend  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai", "scripted"])
    ap.add_argument("--base", default="http://192.168.1.179:11434")
    ap.add_argument("--model", default="huihui_ai/gemma-4-abliterated:e4b")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--system", default="You are a playful, teasing companion. Keep replies to one short sentence.")
    ap.add_argument("--prompt", default="Greet me.")
    args = ap.parse_args()

    backend = make_backend(
        args.backend, base_url=args.base, model=args.model, api_key=args.api_key,
        scripted_corpus=["Hey you.", "Back already?", "Good pet.", "Eyes on the screen."],
    )
    print(f"== backend={backend.name} model={args.model} base={args.base} ==", flush=True)

    messages = [
        {"role": "system", "content": args.system},
        {"role": "user", "content": args.prompt},
    ]

    result = {"err": None, "done": False, "tokens": 0}
    t0 = time.monotonic()
    first = [None]

    def on_token(tok: str) -> None:
        if first[0] is None:
            first[0] = time.monotonic() - t0
        result["tokens"] += 1
        sys.stdout.write(tok)
        sys.stdout.flush()

    def on_done(full: str) -> None:
        result["done"] = True

    def on_error(exc: Exception) -> None:
        result["err"] = exc

    backend.stream(messages, on_token, on_done, on_error)

    dt = time.monotonic() - t0
    print("\n---")
    if result["err"]:
        print(f"ERROR: {type(result['err']).__name__}: {result['err']}")
        return 1
    ttft = f"{first[0]*1000:.0f}ms" if first[0] is not None else "n/a"
    print(f"ok done={result['done']} chunks={result['tokens']} ttft={ttft} total={dt:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
