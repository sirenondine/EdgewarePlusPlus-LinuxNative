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

# Detached session-memory extractor. Quitting must feel instant, but learning
# durable facts is a (potentially slow) LLM call. The engine writes the session
# log + backend config to a temp JSON and spawns this module as a separate
# process, then exits immediately; this process does the blocking LLM work and
# persists the facts on its own time. Run as: python -m features.companion.extract <json>

import json
import logging
import os
import sys


def main(path: str) -> None:
    from features.companion import llm, memory
    from features.companion.engine import _MEMORY_SYSTEM, _MEMORY_TIMEOUT, _parse_facts

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    log = "\n".join(data.get("log", []))
    if not log.strip():
        return

    backend = llm.make_backend(
        data.get("backend", "scripted"),
        base_url=data.get("base_url"),
        model=data.get("model"),
        api_key=data.get("api_key"),
        scripted_corpus=[],
        timeout=_MEMORY_TIMEOUT,
    )
    messages = [
        {"role": "system", "content": _MEMORY_SYSTEM},
        {"role": "user", "content": f"Session log:\n{log}\n\nList durable facts about the user, one per line, or 'none'."},
    ]
    acc: list[str] = []
    backend.stream(messages, lambda t: acc.append(t), lambda f: None,
                   lambda e: logging.warning(f"memory extraction error: {e}"))
    facts = _parse_facts("".join(acc))
    if facts:
        memory.add_facts(facts)
        logging.info(f"Companion learned {len(facts)} fact(s) (detached).")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            main(sys.argv[1])
        except Exception as e:
            logging.warning(f"detached memory extraction failed: {e}")
        finally:
            try:
                os.remove(sys.argv[1])
            except OSError:
                pass
