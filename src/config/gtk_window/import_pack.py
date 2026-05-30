import os
import shutil
import zipfile
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from config.gtk_window.toast import toast
from config.gtk_window.utils import confirm_overwrite, refresh
from paths import DEFAULT_PACK_PATH, Data, PackPaths


def _dialog(title: str, text: str) -> None:
    from gtk_dialog import ask_yes_no
    ask_yes_no(title, text)


def import_pack(default: bool) -> None:
    file_dialog = Gtk.FileDialog.new()
    file_dialog.set_title("Select Pack Zip")
    filt = Gtk.FileFilter()
    filt.set_name("Zip files")
    filt.add_mime_type("application/zip")
    file_dialog.set_default_filter(filt)
    file_dialog.open(None, None, _on_import_file_selected, default)


def extract_pack(zip_path: Path, default: bool = False) -> tuple[bool, str]:
    """Extract a pack zip into the packs dir (or default resource). Returns
    (success, message_or_location). Handles single-subdir-wrapped zips."""
    if not zipfile.is_zipfile(zip_path):
        return False, "Selected file is not a zip file."

    pack_name = zip_path.with_suffix("").name
    import_location = DEFAULT_PACK_PATH if default else Data.PACKS / pack_name

    if not confirm_overwrite(import_location):
        return False, "Pack import cancelled."

    with zipfile.ZipFile(zip_path, "r") as z:
        import_location.mkdir(parents=True, exist_ok=True)
        z.extractall(import_location)

    pack_paths = PackPaths(import_location)
    check_vars = [v for v in vars(pack_paths) if v not in ["root", "splash"]]

    def paths_exist():
        return any(getattr(pack_paths, v).exists() for v in check_vars)

    if not paths_exist():
        files = os.listdir(import_location)
        if len(files) != 1 or not (import_location / files[0]).is_dir():
            return False, "Pack appears to be incorrectly packaged, unable to recover."
        subdir = import_location / files[0]
        for f in os.listdir(subdir):
            shutil.move(subdir / f, import_location / f)
        subdir.rmdir()

    if not paths_exist():
        return False, "Pack appears to be incorrectly packaged, unable to recover."

    return True, str(import_location)


def _on_import_file_selected(fd: Gtk.FileDialog, result: Gio.AsyncResult, default: bool) -> None:
    try:
        file = fd.open_finish(result)
    except Exception:
        return
    if not file:
        return

    ok, message = extract_pack(Path(file.get_path()), default)
    if not ok:
        if message == "Pack import cancelled.":
            toast(message)
        else:
            _dialog("Error", message)
        return

    toast(f'Pack imported to "{message}".')
    refresh()
