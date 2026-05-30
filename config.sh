#!/bin/bash
cd ~/.local/share/edgeware && GDK_BACKEND=wayland GSK_RENDERER=gl .venv/bin/python3 src/main_config.py "$@"
