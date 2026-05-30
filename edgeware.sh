#!/bin/bash
cd ~/.local/share/edgeware || exit 1

# Control subcommands talk to a running instance over the panic socket:
#   edgeware.sh panic     stop everything and revert the wallpaper
#   edgeware.sh pause     stop spawning new popups
#   edgeware.sh resume    resume
#   edgeware.sh toggle    flip the pause state
#   edgeware.sh status    print running / paused / popup count
# With no argument, edgeware.sh starts Edgeware.
case "$1" in
  panic|pause|resume|toggle|status)
    exec .venv/bin/python3 src/panic.py "$1"
    ;;
esac

# Preload gtk4-layer-shell before libwayland-client (it must load first).
# Doing it here means Python starts once; the in-process re-exec fallback in
# main_edgeware.py only kicks in when launched directly without this.
LAYER_LIB=$(ldconfig -p 2>/dev/null | grep -m1 'libgtk4-layer-shell\.so' | awk '{print $NF}')
[ -z "$LAYER_LIB" ] && LAYER_LIB=$(ls /usr/lib*/libgtk4-layer-shell.so* 2>/dev/null | head -1)
export LD_PRELOAD="${LAYER_LIB}${LD_PRELOAD:+ $LD_PRELOAD}"

export GDK_BACKEND=wayland GSK_RENDERER=gl
exec .venv/bin/python3 src/main_edgeware.py "$@"
