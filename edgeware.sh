#!/bin/bash
cd ~/.local/share/edgeware || exit 1

# Preload gtk4-layer-shell before libwayland-client (it must load first).
# Doing it here means Python starts once; the in-process re-exec fallback in
# main_edgeware.py only kicks in when launched directly without this.
LAYER_LIB=$(ldconfig -p 2>/dev/null | grep -m1 'libgtk4-layer-shell\.so' | awk '{print $NF}')
[ -z "$LAYER_LIB" ] && LAYER_LIB=$(ls /usr/lib*/libgtk4-layer-shell.so* 2>/dev/null | head -1)
export LD_PRELOAD="${LAYER_LIB}${LD_PRELOAD:+ $LD_PRELOAD}"

export GDK_BACKEND=wayland GSK_RENDERER=gl
exec .venv/bin/python3 src/main_edgeware.py "$@"
