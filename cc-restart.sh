#!/bin/sh
# Emergency (Super+Shift+Tab): kill a stuck command center and start a fresh daemon.
# Own file + python-anchored pattern, so it never matches a shell or an editor with this path open.
pkill -9 -f '^python[0-9.]* [^ ]*command_center\.py'
sleep 0.3
exec "$HOME/.config/hypr/command_center.py" --daemon
