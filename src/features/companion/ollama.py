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

# Ollama introspection for the config UI: list installed models and report each
# model's capabilities (e.g. vision, tools). Blocking HTTP — call off the main
# thread.

import logging


def list_models(base_url: str) -> list[str]:
    """Installed model names from GET /api/tags, or empty on failure."""
    import requests
    try:
        base = (base_url or "http://localhost:11434").rstrip("/")
        data = requests.get(f"{base}/api/tags", timeout=4).json()
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    except Exception as e:
        logging.info(f"Ollama model list failed ({base_url}): {e}")
        return []


def capabilities(base_url: str, model: str) -> set[str]:
    """A model's capabilities (e.g. {'completion', 'tools', 'vision'}) from
    POST /api/show, or empty on failure / older Ollama."""
    import requests
    try:
        base = (base_url or "http://localhost:11434").rstrip("/")
        data = requests.post(f"{base}/api/show", json={"model": model}, timeout=5).json()
        return {str(c).lower() for c in data.get("capabilities", [])}
    except Exception as e:
        logging.debug(f"Ollama capabilities failed ({model}): {e}")
        return set()


def models_with_capabilities(base_url: str) -> list[tuple[str, set[str]]]:
    """(name, capabilities) for every installed model."""
    return [(name, capabilities(base_url, name)) for name in list_models(base_url)]
