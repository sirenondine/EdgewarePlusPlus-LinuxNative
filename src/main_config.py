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
import sys

from paths import Data

# Fix scaling on high resolution displays
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(0)
except Exception:
    pass

os.environ["PATH"] += os.pathsep + str(Data.ROOT)

import logging
import traceback

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


def main() -> None:
    try:
        from config.gtk_window import ConfigWindow
        win = ConfigWindow()
        GLib.MainLoop().run()
    except Exception as e:
        logging.fatal(f"Config encountered fatal error: {e}\n\n{traceback.format_exc()}")
        dialog = Gtk.AlertDialog()
        dialog.set_message("Could not start")
        dialog.set_detail(f"Could not start config.\n[{e}]")
        dialog.show()


if __name__ == "__main__":
    main()
