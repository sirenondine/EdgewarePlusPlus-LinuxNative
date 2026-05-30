#!/bin/bash
cd ~/.local/share/edgeware && GDK_BACKEND=wayland,x11 GSK_RENDERER=gl .venv/bin/python3 src/main_config.py "$@"
