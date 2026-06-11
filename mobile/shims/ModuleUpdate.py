"""Mobile shim for the monorepo's ModuleUpdate module: the on-device world store.

Desktop installs game worlds as `worlds.<slug>` wheels via a uv subprocess
into mwgg_venv. There is no pip/uv on Android or iOS, but a pure-Python wheel
is just a zip laid out for site-packages — so this shim downloads the wheel
from the URL in the game index (`GameIndex` entry `module_location`) and
extracts it, payload + dist-info, into mwgg_venv_site_packages().

main.py sets MWGG_USE_WORLDS_VENV=1 and puts that directory on sys.path, so:
  * `worlds/__init__` extends its __path__ with .../site-packages/worlds —
    extracted worlds import exactly like desktop venv installs;
  * `importlib.metadata.distribution("worlds.<slug>")` resolves (dist-info is
    extracted too), which `Utils.set_game_names` and update checks rely on.

Only pure wheels (`py3-none-any`) are accepted: there is no compiler on the
device, and platform wheels would target the wrong ABI anyway.

Surface kept to what the vendored modules and mwgg_gui actually call:
install_worlds, uninstall_worlds, find_world_modules, custom_worlds_dir,
install_mwgg_igdb, set_variant, check_for_updates.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import logging
import shutil
import zipfile
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from BaseUtils import mwgg_venv_site_packages, write_path

logger = logging.getLogger("Update")

# Parity with frozen desktop: user-writable directory scanned for hand-dropped
# .apworld files (Utils.register_custom_worlds reads this).
custom_worlds_dir = Path(write_path("custom_worlds"))
custom_worlds_dir.mkdir(parents=True, exist_ok=True)

_DOWNLOAD_TIMEOUT = 120


def _site_packages() -> Path:
    path = Path(mwgg_venv_site_packages())
    path.mkdir(parents=True, exist_ok=True)
    return path


def _worlds_dir() -> Path:
    path = _site_packages() / "worlds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _venv_worlds_dir() -> Path:
    """Kept name-compatible with desktop ModuleUpdate (Generate uses it)."""
    return _worlds_dir()


def _game_index():
    from mwgg_igdb import GameIndex
    return GameIndex


def _world_slug(world: str) -> str:
    return world.removeprefix("worlds.")


def _installed_version(slug: str) -> str | None:
    try:
        return importlib.metadata.distribution(f"worlds.{slug}").version
    except importlib.metadata.PackageNotFoundError:
        return None


def _wheel_url_for(slug: str) -> str | None:
    entry = _game_index().get_all_games().get(slug) or {}
    url = entry.get("module_location")
    return url if isinstance(url, str) and url else None


def _wheel_version(url: str) -> str | None:
    """PEP 427: dist-version-...whl; version is the second dash segment."""
    name = url.rsplit("/", 1)[-1].split("#", 1)[0].split("?", 1)[0]
    if not name.endswith(".whl"):
        return None
    parts = name[: -len(".whl")].split("-")
    return parts[1] if len(parts) >= 5 else None


def _download(url: str) -> bytes:
    import requests
    clean = url.split("#", 1)[0]
    logger.info("world store: downloading %s", clean)
    response = requests.get(clean, timeout=_DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    payload = response.content
    fragment = urlparse(url).fragment
    if fragment.startswith("sha256="):
        expected = fragment[len("sha256="):].lower()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise RuntimeError(f"sha256 mismatch for {clean}: {actual} != {expected}")
    return payload


def _assert_pure_wheel(url: str, names: list[str]) -> None:
    filename = url.rsplit("/", 1)[-1].split("#", 1)[0]
    if "py3-none-any" not in filename:
        raise RuntimeError(
            f"{filename} is not a pure-Python wheel; this world cannot run on mobile."
        )
    for name in names:
        if name.endswith((".so", ".pyd", ".dll", ".dylib")):
            raise RuntimeError(
                f"{filename} contains a native extension ({name}); "
                "this world cannot run on mobile."
            )


def _extract_wheel(payload: bytes, slug: str) -> None:
    import io
    site = _site_packages()
    with zipfile.ZipFile(io.BytesIO(payload)) as wheel:
        names = wheel.namelist()
        _assert_pure_wheel(_wheel_url_for(slug) or f"worlds.{slug}.whl", names)
        for member in names:
            target = (site / member).resolve()
            if not str(target).startswith(str(site.resolve())):
                raise RuntimeError(f"wheel member escapes site-packages: {member}")
        wheel.extractall(site)
    importlib.invalidate_caches()


def _remove_world(slug: str) -> None:
    removed = False
    world_dir = _worlds_dir() / slug
    if world_dir.is_dir():
        shutil.rmtree(world_dir, ignore_errors=True)
        removed = True
    for dist_info in _site_packages().glob(f"worlds.{slug}-*.dist-info"):
        shutil.rmtree(dist_info, ignore_errors=True)
        removed = True
    # Wheel dist names may normalize dots to underscores.
    for dist_info in _site_packages().glob(f"worlds_{slug}-*.dist-info"):
        shutil.rmtree(dist_info, ignore_errors=True)
        removed = True
    if removed:
        importlib.invalidate_caches()


def install_worlds(worlds: List[str], update: bool = False, with_deps: bool = False) -> list[str]:
    """Download + extract each requested world's wheel. Returns the list of
    slugs that fell back to a custom apworld — always empty on mobile (wheel
    or nothing), matching the desktop return contract.

    with_deps is accepted for signature parity; world wheels are expected to
    be self-contained on mobile (their pip dependencies cannot be installed
    on device — incompatible worlds fail at import with a logged error).
    """
    for world in worlds:
        slug = _world_slug(world)
        if slug.startswith("mwgg_igdb"):
            set_variant(slug.removeprefix("mwgg_igdb_") or "sixteen")
            continue
        url = _wheel_url_for(slug)
        if url is None:
            logger.warning("world store: no module_location for %s; skipping", slug)
            continue
        installed = _installed_version(slug)
        wanted = _wheel_version(url)
        if installed is not None and not update and (wanted is None or installed == wanted):
            continue
        try:
            payload = _download(url)
            if installed is not None:
                _remove_world(slug)
            _extract_wheel(payload, slug)
            logger.info("world store: installed worlds.%s %s", slug, wanted or "")
        except Exception:
            logger.exception("world store: failed to install %s", slug)
    return []


def uninstall_worlds(worlds: List[str]) -> None:
    for world in worlds:
        slug = _world_slug(world)
        if slug.startswith("mwgg_igdb"):
            continue  # the index snapshot is bundled; variants switch via set_variant
        _remove_world(slug)


def find_world_modules() -> set[str]:
    """All known world slugs: union of game-index entries and locally
    extracted worlds (mirrors the desktop union of index + installed dists)."""
    modules: set[str] = set(_game_index().get_all_games().keys())
    for entry in _worlds_dir().iterdir():
        if entry.is_dir() and not entry.name.startswith("_"):
            modules.add(entry.name)
    return modules


def check_for_updates(worlds_only: bool = False) -> List[str]:
    """Slugs whose extracted version differs from the index wheel tag."""
    outdated: List[str] = []
    for slug, entry in _game_index().get_all_games().items():
        url = entry.get("module_location")
        if not isinstance(url, str) or not url:
            continue
        wanted = _wheel_version(url)
        installed = _installed_version(slug)
        if installed is not None and wanted is not None and installed != wanted:
            outdated.append(f"worlds.{slug}")
    return outdated


def update(yes: bool = True, force: bool = False, worlds: List[str] | None = None) -> None:
    """Desktop refreshes requirements.txt deps here; on mobile all Python
    dependencies are baked into the app bundle, so only world installs apply."""
    if worlds:
        install_worlds(worlds, update=force)


def is_frozen() -> bool:
    """The mobile bundle behaves like a frozen build for ModuleUpdate's
    callers (no pip, no source checkout)."""
    return True


def install_mwgg_igdb(upgrade: bool = False) -> bool:
    """The index ships bundled in the app (vendor/mwgg_igdb.py); runtime
    refresh is not implemented yet. Returns importability."""
    try:
        _game_index()
        return True
    except ImportError:
        return False


def set_variant(variant: str) -> None:
    """Parental-rating index variants require swapping the mwgg_igdb module;
    not supported on device yet (the bundled variant is fixed at build time)."""
    logger.warning(
        "world store: switching the age-rating index variant (%s) is not "
        "supported on mobile yet; the bundled index stays active.", variant,
    )
