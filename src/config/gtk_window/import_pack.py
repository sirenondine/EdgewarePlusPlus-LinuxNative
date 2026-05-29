import os
import shutil
import zipfile
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.gtk_window.utils import confirm_overwrite, refresh
from paths import DEFAULT_PACK_PATH, Data, PackPaths


def import_pack(default: bool) -> None:
    dialog = Gtk.FileChooserNative(
        title="Select Pack Zip",
        accept_label="Open",
        cancel_label="Cancel",
    )
    filt = Gtk.FileFilter()
    filt.set_name("Zip files")
    filt.add_mime_type("application/zip")
    dialog.add_filter(filt)

    if dialog.run() != Gtk.ResponseType.ACCEPT:
        dialog.destroy()
        return

    pack_zip = dialog.get_file()
    dialog.destroy()
    if not pack_zip:
        return

    zip_path = Path(pack_zip.get_path())

    if not zipfile.is_zipfile(zip_path):
        err = Gtk.MessageDialog(text="Error", secondary_text="Selected file is not a zip file.")
        err.run()
        err.destroy()
        return

    pack_name = zip_path.with_suffix("").name
    import_location = DEFAULT_PACK_PATH if default else Data.PACKS / pack_name

    if not confirm_overwrite(import_location):
        info = Gtk.MessageDialog(text="Cancelled", secondary_text="Pack import cancelled.")
        info.run()
        info.destroy()
        return

    with zipfile.ZipFile(zip_path, "r") as z:
        import_location.mkdir(parents=True, exist_ok=True)
        z.extractall(import_location)

    pack_paths = PackPaths(import_location)
    check_vars = [v for v in vars(pack_paths) if v not in ["root", "splash"]]
    def paths_exist():
        return any(getattr(pack_paths, v).exists() for v in check_vars)

    if not paths_exist():
        files = os.listdir(import_location)
        if len(files) != 1:
            err = Gtk.MessageDialog(text="Error", secondary_text="Pack appears to be incorrectly packaged, unable to recover.")
            err.run()
            err.destroy()
            return

        subdir = import_location / files[0]
        if not subdir.is_dir():
            err = Gtk.MessageDialog(text="Error", secondary_text="Pack appears to be incorrectly packaged, unable to recover.")
            err.run()
            err.destroy()
            return

        for f in os.listdir(subdir):
            shutil.move(subdir / f, import_location / f)
        subdir.rmdir()

    if not paths_exist():
        err = Gtk.MessageDialog(text="Error", secondary_text="Pack appears to be incorrectly packaged, unable to recover.")
        err.run()
        err.destroy()
        return

    done = Gtk.MessageDialog(
        text="Done",
        secondary_text=f'Pack imported to "{import_location}". Refreshing config window.',
    )
    done.run()
    done.destroy()
    refresh()
