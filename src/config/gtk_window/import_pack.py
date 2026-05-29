import os
import shutil
import zipfile
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from config.gtk_window.utils import confirm_overwrite, refresh
from paths import DEFAULT_PACK_PATH, Data, PackPaths


def _dialog(title: str, text: str) -> None:
    d = Gtk.Dialog(title=title)
    d.add_button("OK", Gtk.ResponseType.OK)
    d.get_content_area().append(Gtk.Label(label=text, wrap=True, margin=12))
    d.present()
    d.run()
    d.destroy()


def import_pack(default: bool) -> None:
    file_dialog = Gtk.FileDialog.new()
    file_dialog.set_title("Select Pack Zip")
    filt = Gtk.FileFilter()
    filt.set_name("Zip files")
    filt.add_mime_type("application/zip")
    file_dialog.set_default_filter(filt)
    file_dialog.open(None, _on_import_file_selected, default)


def _on_import_file_selected(fd: Gtk.FileDialog, result: Gio.AsyncResult, default: bool) -> None:
    try:
        file = fd.open_finish(result)
    except Exception:
        return
    if not file:
        return

    zip_path = Path(file.get_path())

    if not zipfile.is_zipfile(zip_path):
        _dialog("Error", "Selected file is not a zip file.")
        return

    pack_name = zip_path.with_suffix("").name
    import_location = DEFAULT_PACK_PATH if default else Data.PACKS / pack_name

    if not confirm_overwrite(import_location):
        _dialog("Cancelled", "Pack import cancelled.")
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
            _dialog("Error", "Pack appears to be incorrectly packaged, unable to recover.")
            return
        subdir = import_location / files[0]
        if not subdir.is_dir():
            _dialog("Error", "Pack appears to be incorrectly packaged, unable to recover.")
            return
        for f in os.listdir(subdir):
            shutil.move(subdir / f, import_location / f)
        subdir.rmdir()

    if not paths_exist():
        _dialog("Error", "Pack appears to be incorrectly packaged, unable to recover.")
        return

    _dialog("Done", f'Pack imported to "{import_location}". Refreshing config window.')
    refresh()
