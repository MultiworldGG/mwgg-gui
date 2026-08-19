#!/usr/bin/env python3
"""Assemble the mobile app's vendor tree.

The mobile app (mobile/main.py) is a thin shell over the mwgg_gui package and
a vendored slice of the MultiworldGG monorepo. This script copies everything
the shell needs into mobile/vendor/ (gitignored), which main.py puts on
sys.path after mobile/shims/:

    vendor/
      mwgg_gui/            <- this repo's package
      <module>.py ...      <- monorepo top-level modules (VENDOR_MODULES)
      worlds/              <- monorepo worlds/ package ROOT files only
                              (game worlds arrive at runtime via the world store)
      rule_builder/        <- monorepo package (BaseClasses dependency)
      mwgg_igdb.py         <- game-index snapshot (single pure-python module)
      data/                <- fonts, icon, QOTD, LICENSE  (local_path() root)
      kivy_data/           <- Kivy data dir replacement (recolorable atlas,
                              fonts, images) mirrored to writable storage by
                              main.py at first run

BaseUtils.local_path() resolves to the directory containing BaseUtils.py, so
the vendor dir doubles as the "MultiworldGG install root" on device — data/
must live next to the vendored modules.

Usage:
    python sync_vendor.py [--monorepo PATH] [--check-only]

The monorepo defaults to a sibling checkout (../../MultiworldGG/src relative
to this file's repo, or the MWGG_MONOREPO env var). CI checks the monorepo
out next to this repo.
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # mobile/
REPO = HERE.parent                              # mwgg-gui checkout
VENDOR = HERE / "vendor"

# Monorepo top-level modules the GUI + client runtime import (closure verified
# against the monorepo; check_import_closure() re-verifies on every sync).
VENDOR_MODULES = [
    "APContainer",
    "BaseClasses",
    "BaseUtils",
    "ClientBuilder",
    "ClientState",
    "CommonClient",
    "entrance_rando",
    "FileUtils",
    "Fill",
    "frontend_protocol",
    "Generate",  # Universal Tracker regenerates in-process (TrackerCore -> Generate.main)
    "kvui",
    "Main",      # Generate -> Main.main (ERmain); closure is already vendored
    "NetUtils",
    "Options",
    "settings",
    "ui_dataclasses",
    "Utils",
]

# Monorepo modules deliberately NOT vendored: mobile/shims/ provides
# device-appropriate replacements that shadow them on sys.path.
SHIMMED_MODULES = {"ModuleUpdate", "MultiServer", "jellyfish"}

# worlds/ package: root files plus the infrastructure worlds that are part of
# the runtime, not game content. Actual game worlds (worlds.<slug>) are
# downloaded at runtime; worlds/__init__ extends its __path__ to find them.
WORLDS_ROOT_FILES = [
    "__init__.py",
    "AutoSNIClient.py",
    "AutoWorld.py",
    "Files.py",
    "LauncherComponents.py",
]
WORLDS_PACKAGES = [
    "generic",   # base rules world — Fill imports worlds.generic.Rules
    "tracker",   # Universal Tracker — core mobile client type
    "_manual",   # Manual-world client framework — launcher's Manual client type
]

VENDOR_PACKAGES = ["rule_builder"]

# Names that may appear as imports in vendored code and are satisfied by
# pip-installed requirements (buildozer.spec / kivy-ios) or the stdlib-adjacent
# environment, not by vendoring.
PIP_SATISFIED = {
    "kivy", "kivymd", "asynckivy", "asyncgui", "materialyoucolor", "PIL",
    "numpy", "websockets", "yaml", "requests", "certifi", "nest_asyncio",
    "pathspec", "typing_extensions", "colorama", "pygments", "exceptiongroup",
    "android", "ios", "jnius", "pyobjus", "plyer",
    "mwgg_igdb",          # snapshot copied into vendor/
    "mwgg_gui",           # copied into vendor/
    "mwgg_splash", "mwgg_tui",  # desktop-only, behind platform/env gates
    "sqlalchemy",         # MultiServer (shimmed) — never imported on device
    "pymem", "dolphin_memory_engine", "win32gui", "win32con", "win32file",
    "tkinter",            # desktop-only guarded imports
    "schema", "websiterewrite", "WebHostLib", "GitHubLib",
    "ModuleUpdate", "MultiServer", "jellyfish",  # shimmed
    "bsdiff4", "zstandard",  # APContainer/Files patch containers (world-store extras)
    "packaging", "platformdirs",  # pure-python, in requirements
    "openpyxl",   # kvui legacy helper, lazy import, pure-python
    "jinja2",     # Options yaml-template generation, lazy import, unused on mobile
    "Launcher",   # legacy AP component launching, lazy import, unused on mobile
    "win32com",   # FileUtils win32 dialogs, guarded with Kivy fallback
    "__main__",   # runtime introspection, always present
    "_speedups", "pyximport",  # NetUtils cython fast path, guarded with pure fallback
}


def find_monorepo(cli_value: str | None) -> Path:
    candidates = []
    if cli_value:
        candidates.append(Path(cli_value))
    if os.environ.get("MWGG_MONOREPO"):
        candidates.append(Path(os.environ["MWGG_MONOREPO"]))
    candidates.append(REPO.parent / "MultiworldGG" / "src")
    candidates.append(REPO.parent.parent / "MultiworldGG" / "src")
    # Worktree layout: <main-repo>/.claude/worktrees/<name> — hop to siblings
    # of the main checkout as well.
    for parent in REPO.parents:
        candidates.append(parent / "MultiworldGG" / "src")
    for c in candidates:
        if (c / "BaseUtils.py").is_file():
            return c.resolve()
    raise SystemExit(
        "MultiworldGG monorepo not found. Pass --monorepo or set MWGG_MONOREPO "
        "to its src/ directory."
    )


def find_mwgg_igdb(monorepo: Path) -> Path:
    override = os.environ.get("MWGG_IGDB_PATH")
    if override and Path(override).is_file():
        return Path(override)
    hits = list(monorepo.glob(".venv/Lib/site-packages/mwgg_igdb.py")) \
        + list(monorepo.glob("venv/Lib/site-packages/mwgg_igdb.py")) \
        + list(monorepo.glob(".venv/lib/python*/site-packages/mwgg_igdb.py")) \
        + list(monorepo.glob("venv/lib/python*/site-packages/mwgg_igdb.py"))
    if hits:
        return hits[0]
    raise SystemExit(
        "mwgg_igdb.py not found in the monorepo venvs. Install it there or set "
        "MWGG_IGDB_PATH to the module file."
    )


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".mypy_cache",
            "test", "tests", "docs", "fuzzer_hook.py",
        ),
        dirs_exist_ok=True,
    )


def sync(monorepo: Path) -> None:
    if VENDOR.exists():
        shutil.rmtree(VENDOR)
    VENDOR.mkdir(parents=True)

    # 1. mwgg_gui package from this repo
    copy_tree(REPO / "mwgg_gui", VENDOR / "mwgg_gui")

    # 2. monorepo top-level modules
    for mod in VENDOR_MODULES:
        copy_file(monorepo / f"{mod}.py", VENDOR / f"{mod}.py")

    # 3. worlds/ root files + packages
    for name in WORLDS_ROOT_FILES:
        copy_file(monorepo / "worlds" / name, VENDOR / "worlds" / name)
    for pkg in WORLDS_PACKAGES:
        copy_tree(monorepo / "worlds" / pkg, VENDOR / "worlds" / pkg)
    for pkg in VENDOR_PACKAGES:
        copy_tree(monorepo / pkg, VENDOR / pkg)

    # 4. game index snapshot
    copy_file(find_mwgg_igdb(monorepo), VENDOR / "mwgg_igdb.py")

    # 5. data assets (vendor/ is the local_path() root on device)
    copy_tree(monorepo / "data" / "fonts", VENDOR / "data" / "fonts")
    for name in ("icon.png", "QOTD.txt"):
        copy_file(monorepo / "data" / name, VENDOR / "data" / name)
    copy_file(monorepo / "LICENSE", VENDOR / "LICENSE")

    # 6. Kivy data dir replacement (mirrored to writable storage at first run)
    copy_tree(monorepo / "kivy" / "data", VENDOR / "kivy_data")

    print(f"vendor tree assembled at {VENDOR}")


def _top_level_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        raise SystemExit(f"syntax error in vendored file {path}: {e}")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def check_import_closure() -> None:
    """Every absolute import in the vendor tree must resolve to: stdlib, a
    vendored module/package, a shim, or a pip requirement. Fails loudly on
    anything else so a monorepo refactor can't silently break the APK."""
    vendored = {p.stem for p in VENDOR.glob("*.py")}
    vendored |= {p.name for p in VENDOR.iterdir() if p.is_dir()}
    allowed = vendored | SHIMMED_MODULES | PIP_SATISFIED | set(sys.stdlib_module_names)
    problems: list[str] = []
    for py in VENDOR.rglob("*.py"):
        if "kivy_data" in py.parts:
            continue
        for name in sorted(_top_level_imports(py)):
            if name not in allowed:
                problems.append(f"{py.relative_to(VENDOR)}: {name}")
    if problems:
        print("Unresolved imports in vendor tree:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)
    print("import closure OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monorepo", help="Path to the MultiworldGG src/ directory")
    parser.add_argument("--check-only", action="store_true",
                        help="Only run the import-closure check on an existing vendor tree")
    args = parser.parse_args()
    if not args.check_only:
        sync(find_monorepo(args.monorepo))
    check_import_closure()


if __name__ == "__main__":
    main()
