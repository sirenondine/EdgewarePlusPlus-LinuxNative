#!/bin/bash

version_string=$(python3 --version)
if [ $? -ne 0 ]; then
    echo "Python not found"
    echo "Please install Python 3 and try again"
    exit
fi

IFS=" " read -r p version <<< "$version_string"
IFS="." read -r major minor patch <<< "$version"
if (( !($major == 3 && $minor >= 12) )); then
    echo "Python version 3.12 or higher recommended"
fi

# gtk4-layer-shell positions the runtime popups as Wayland overlay surfaces.
if ! ldconfig -p 2>/dev/null | grep -q "libgtk4-layer-shell" \
    && ! ls /usr/lib*/libgtk4-layer-shell.so* >/dev/null 2>&1 \
    && ! ls /usr/lib/*/libgtk4-layer-shell.so* >/dev/null 2>&1; then
    echo "gtk4-layer-shell not found"
    echo "Please install gtk4-layer-shell (Arch: gtk4-layer-shell, Fedora: gtk4-layer-shell, Debian/Ubuntu: libgtk4-layer-shell0) and try again"
    exit
fi

# gtk4paintablesink (from gst-plugins-rs) renders video/animated popups.
if ! gst-inspect-1.0 gtk4paintablesink >/dev/null 2>&1; then
    echo "GStreamer gtk4paintablesink not found"
    echo "Please install the GStreamer Rust plugins (Arch: gst-plugins-rs, Fedora: gstreamer1-plugins-rs, Debian/Ubuntu: gstreamer1.0-plugins-rs) and try again"
    exit
fi

cd ~/.local/share/edgeware && python3 -m venv .venv
if [ $? -eq 0 ]; then
    source .venv/bin/activate
else
    echo "Failed to create virtual environment"
    exit
fi

cd ~/.local/share/edgeware && python3 -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install requirements"
    exit
fi

shortcut() {
    source=$1
    script=${2:-$1}

    if [ ! -f "$script.sh" ]; then
        echo "#!/bin/bash" >> $script.sh
        echo ".venv/bin/python3 src/${source}.py" >> $script.sh
        chmod +x $script.sh
    fi
}

shortcut "main_edgeware" "edgeware"
shortcut "main_config" "config"
shortcut "panic"
