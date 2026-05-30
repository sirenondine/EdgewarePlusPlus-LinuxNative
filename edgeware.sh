#!/bin/bash
# main_edgeware self-preloads gtk4-layer-shell (re-exec) and sets GDK_BACKEND/
# GSK_RENDERER in-process; the env vars here are just explicit hints.
cd ~/.local/share/edgeware && GDK_BACKEND=wayland GSK_RENDERER=gl .venv/bin/python3 src/main_edgeware.py
