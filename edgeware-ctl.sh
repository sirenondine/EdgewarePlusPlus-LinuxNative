#!/bin/bash
# Edgeware++ runtime control. Sends a command to a running instance over the
# panic Unix socket. Commands: panic | pause | resume | toggle
# Examples:
#   edgeware-ctl.sh pause     # stop spawning popups
#   edgeware-ctl.sh resume    # resume
#   edgeware-ctl.sh toggle    # flip pause state
#   edgeware-ctl.sh panic     # full panic (same as panic.sh)
cd ~/.local/share/edgeware && .venv/bin/python3 src/panic.py "$@"
