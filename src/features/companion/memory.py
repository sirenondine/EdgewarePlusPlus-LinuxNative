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

# Companion long-term auto-memory: a small, capped list of discrete fact
# strings the companion has learned about the user, persisted locally and
# user-editable. The engine extracts facts at session end; both the runtime
# and the config window read/write this file directly. Local only.

import json
import logging
import os
import tempfile

from paths import Data

MAX_FACTS = 30


def _normalize(fact: str) -> str:
    return " ".join(fact.lower().split())


def load_facts() -> list[str]:
    try:
        data = json.loads(Data.COMPANION_MEMORY.read_text(encoding="utf-8"))
        return [str(f) for f in data.get("facts", []) if str(f).strip()]
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.warning(f"Companion memory load failed: {e}")
        return []


def save_facts(facts: list[str]) -> None:
    facts = [f.strip() for f in facts if f.strip()][:MAX_FACTS]
    try:
        Data.COMPANION_MEMORY.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=Data.COMPANION_MEMORY.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"facts": facts}, f, indent=2)
        os.replace(tmp, Data.COMPANION_MEMORY)
    except Exception as e:
        logging.warning(f"Companion memory save failed: {e}")


def add_facts(new_facts: list[str]) -> list[str]:
    """Merge new facts in, skipping near-duplicates, capped (newest kept)."""
    facts = load_facts()
    seen = {_normalize(f) for f in facts}
    for fact in new_facts:
        fact = fact.strip()
        if fact and _normalize(fact) not in seen:
            facts.append(fact)
            seen.add(_normalize(fact))
    if len(facts) > MAX_FACTS:
        facts = facts[-MAX_FACTS:]  # keep the most recent
    save_facts(facts)
    return facts


def clear() -> None:
    try:
        Data.COMPANION_MEMORY.unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        logging.warning(f"Companion memory clear failed: {e}")


def as_context() -> str:
    """Bulleted facts for the engine's context block, or empty when none."""
    facts = load_facts()
    return "\n".join(f"- {f}" for f in facts)
