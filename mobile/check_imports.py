"""Import smoke test for the mobile app tree.

Assembles sys.path exactly like main.py (shims -> vendor) with
MWGG_SHELL=mobile, then imports every vendored monorepo module, the shims,
and mwgg_gui.app. Catches missing vendor closure, desktop-only imports, and
shell-bootstrap regressions in minutes instead of a full APK build.

All writable roots (KIVY_HOME, write_path, user_path) are redirected into a
temp sandbox so running this locally can never touch a real MultiworldGG
install's config. Requires a display (CI runs it under xvfb-run) because
importing mwgg_gui.app creates the Kivy window.

Usage: python mobile/check_imports.py
"""
import importlib
import os
import sys
import tempfile
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SHIMS = os.path.join(APP_DIR, "shims")
VENDOR = os.path.join(APP_DIR, "vendor")
sys.path.insert(0, VENDOR)
sys.path.insert(0, SHIMS)

SANDBOX = tempfile.mkdtemp(prefix="mwgg_mobile_imports_")

os.environ["MWGG_SHELL"] = "mobile"
os.environ["MWGG_FRONTEND"] = "gui"
os.environ["KIVY_NO_ARGS"] = "1"
os.environ["MWGG_USE_WORLDS_VENV"] = "1"
os.environ["KIVY_HOME"] = os.path.join(SANDBOX, "kivy_home")
os.makedirs(os.environ["KIVY_HOME"], exist_ok=True)
os.environ["KIVY_DATA_DIR"] = os.path.join(VENDOR, "kivy_data")

import BaseUtils  # noqa: E402

BaseUtils.local_path.cached_path = VENDOR
# Redirect every writable root into the sandbox BEFORE any other module binds
# write_path/user_path (vendored modules import them from BaseUtils at their
# own import time, which happens after this line).
BaseUtils.write_path = lambda *path: os.path.join(SANDBOX, "write", *path)
BaseUtils.user_path.cached_path = os.path.join(SANDBOX, "user")
os.makedirs(BaseUtils.user_path.cached_path, exist_ok=True)
os.makedirs(BaseUtils.write_path(), exist_ok=True)

world_site = BaseUtils.mwgg_venv_site_packages()
os.makedirs(world_site, exist_ok=True)
sys.path.append(world_site)

MODULES = [
    # shims first (they shadow the monorepo names)
    "MultiServer",
    "ModuleUpdate",
    # vendored monorepo slice
    "BaseUtils",
    "NetUtils",
    "APContainer",
    "ClientState",
    "FileUtils",
    "settings",
    "Utils",
    "Options",
    "BaseClasses",
    "Fill",
    "entrance_rando",
    "ui_dataclasses",
    "frontend_protocol",
    "worlds",
    "worlds.AutoWorld",
    "worlds.LauncherComponents",
    "worlds.Files",
    "worlds.generic",
    "mwgg_igdb",
    "CommonClient",
    "ClientBuilder",
    "Generate",
    "Main",
    "worlds.tracker",
    "worlds.tracker.TrackerClient",
    "worlds._manual",
    # the GUI package (imports kivy.core.window -> needs a display)
    "mwgg_gui.app",
    "mwgg_gui.bootstrap",
    "mwgg_gui.components.layout_mode",
    "mwgg_gui.yaml_creator",
    "kvui",
]

failures: list[tuple[str, str]] = []
for name in MODULES:
    try:
        importlib.import_module(name)
        print(f"ok   {name}", flush=True)
    except Exception:
        failures.append((name, traceback.format_exc()))
        print(f"FAIL {name}", flush=True)

# Shim sanity: the shims must have won over any same-named vendored module.
import MultiServer  # noqa: E402
import ModuleUpdate  # noqa: E402
for mod in (MultiServer, ModuleUpdate):
    if not getattr(mod, "__file__", "").startswith(SHIMS):
        failures.append((mod.__name__, f"resolved outside shims: {mod.__file__}"))

# Shell sanity: the mobile shell must not have set desktop window geometry.
try:
    from kivy.config import Config
    width = Config.getdefault("graphics", "width", "")
    if width == "1099":
        failures.append(("bootstrap", "mobile shell applied desktop window geometry"))
except Exception:
    failures.append(("kivy.config", traceback.format_exc()))

if failures:
    print(f"\n{len(failures)} import failure(s):", flush=True)
    for name, tb in failures:
        print(f"\n=== {name} ===\n{tb}", flush=True)
    sys.exit(1)
print("\nall mobile imports OK", flush=True)
