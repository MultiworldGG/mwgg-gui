"""
Setup-guide resolution for the launcher's play strip.

Index games resolve to a webhost URL; a world added to custom_worlds/ resolves
to whatever `docs/setup*.md` it ships. Archives are read as zips and module
identity comes from their manifests, so no world code is imported here.
"""
from __future__ import annotations

__all__ = ("setup_guide_url", "extract_bundled_setup_doc", "open_with_desktop")

import logging
import os
import subprocess
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Optional

from mwgg_gui.constants import SETUP_GUIDE_URL

logger = logging.getLogger("Client")

# English first, then any other setup doc: a world shipping only a localized
# guide gets opened rather than reported as missing.
_DOC_PREFERENCE = ("setup_en.md", "setup.md")

# Extracted docs share one directory so repeated presses overwrite in place
# instead of piling up temp dirs.
_DOC_CACHE_DIR = "mwgg_setup_docs"


def setup_guide_url(game_name: str) -> str:
    """Webhost URL for a game's setup guide. The route resolves `setup` to
    whatever guide the world declares, so the file name need not be literal.
    """
    return SETUP_GUIDE_URL.format(game=urllib.parse.quote(game_name, safe=""))


def find_setup_doc(archive: zipfile.ZipFile) -> Optional[str]:
    """Name of the archive's setup doc member, or None.

    Worlds nest `docs/` at varying depths (`<module>/docs/` in an .apworld,
    `worlds/<module>/docs/` in a wheel), so members are matched on the
    `docs/setup*.md` tail alone.
    """
    candidates: dict[str, str] = {}
    for name in archive.namelist():
        head, _, base = name.rpartition("/docs/")
        if not head or "/" in base:
            continue
        base = base.lower()
        if base.startswith("setup") and base.endswith(".md"):
            candidates.setdefault(base, name)
    if not candidates:
        return None
    for preferred in _DOC_PREFERENCE:
        if preferred in candidates:
            return candidates[preferred]
    return candidates[min(candidates)]


def find_custom_world_archive(module: str) -> Optional[Path]:
    """The custom_worlds/ archive that supplies `module`, or None.

    File names need not match the module (a wheel is named after its
    distribution), so identity comes from the archive's own manifest.
    """
    import Utils
    from ModuleUpdate import custom_worlds_dir

    for candidate in custom_worlds_dir.iterdir():
        try:
            if Utils.discover_custom_world_module(candidate) == module:
                return candidate
        except Exception:
            logger.warning("Skipping unreadable custom world %s", candidate.name,
                           exc_info=True)
    return None


def extract_bundled_setup_doc(module: str) -> Optional[str]:
    """Write an added world's bundled setup doc to a temp file and return its
    path, or None when the world ships no setup doc.

    Raises OSError if the doc is found but cannot be written.
    """
    archive_path = find_custom_world_archive(module)
    if archive_path is None:
        return None
    with zipfile.ZipFile(archive_path) as archive:
        member = find_setup_doc(archive)
        if member is None:
            return None
        contents = archive.read(member)
    target = os.path.join(tempfile.gettempdir(), _DOC_CACHE_DIR,
                          f"{module}_{os.path.basename(member)}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as doc_file:
        doc_file.write(contents)
    return target


def open_with_desktop(path: str) -> None:
    """Hand a file to the desktop's default handler.

    Raises OSError when the opener can't be spawned, and on Windows also when
    no application is registered for the file type -- the freedesktop and macOS
    openers report that to the user themselves and exit successfully here.
    """
    from Utils import is_macos, is_windows

    if is_windows:
        os.startfile(path)
    elif is_macos:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
