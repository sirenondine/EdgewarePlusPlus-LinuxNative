# Copyright (C) 2024 Araten & Marigold
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

import os

# Wayland-only. Must be set before GTK is imported.
if "GDK_BACKEND" not in os.environ:
    os.environ["GDK_BACKEND"] = "wayland"

# Use the GL renderer to avoid Vulkan VK_SUBOPTIMAL_KHR warning spam.
if "GSK_RENDERER" not in os.environ:
    os.environ["GSK_RENDERER"] = "gl"

import logging
import traceback

from gi import require_version

require_version("Gdk", "4.0")
require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk


def main() -> None:
    app = Adw.Application(application_id="io.github.sirenondine.EdgewarePlusPlus")

    def on_activate(app: Gtk.Application) -> None:
        # Raise existing window on second launch
        windows = app.get_windows()
        if windows:
            windows[0].present()
            return

        # `--import <pack.zip>` (e.g. from a file-manager "Open With"): import the
        # pack, then open the config window normally.
        import sys
        if "--import" in sys.argv:
            idx = sys.argv.index("--import")
            if idx + 1 < len(sys.argv):
                from pathlib import Path
                from config.gtk_window.import_pack import extract_pack
                ok, message = extract_pack(Path(sys.argv[idx + 1]))
                logging.info(f"Pack import {'succeeded' if ok else 'failed'}: {message}")

        try:
            from config.gtk_window import (
                DashboardWindow,
                SettingsWindow,
                build_session,
                fetch_live_version_async,
                maybe_prompt_update,
            )
            vars, pack, local_version, _live = build_session()
            # `edgeware` (dashboard mode) passes --dashboard; `edgeware config`
            # opens the Settings window directly.
            if "--dashboard" in sys.argv:
                window = DashboardWindow(app, vars, pack, local_version, "")
            else:
                window = SettingsWindow(app, vars, pack, local_version, "")

            # The live version is fetched off-thread so the window appears at
            # once; update the display and offer the update prompt when it lands.
            def _on_version(v: str) -> None:
                window.set_live_version(v)
                maybe_prompt_update(local_version, v)
            fetch_live_version_async(_on_version)
        except Exception as e:
            logging.fatal(f"Config encountered fatal error: {e}\n\n{traceback.format_exc()}")
            dialog = Gtk.AlertDialog()
            dialog.set_message("Could not start")
            dialog.set_detail(f"Could not start config.\n[{e}]")
            dialog.show(None)

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    main()
