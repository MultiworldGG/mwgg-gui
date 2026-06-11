"""MultiworldGG mobile entry point (Android via buildozer, iOS via kivy-ios).

The mobile analog of the monorepo's MultiWorld.py, minus everything that
doesn't exist on device: no splash process, no startup world updates, no
frozen-build path juggling. One process, one asyncio loop driving Kivy via
async_run; game clients (text client, Universal Tracker) take over the live
UI in-process exactly as on desktop.

sys.path layout (decreasing precedence):
    shims/   — device replacements that SHADOW monorepo modules
               (ModuleUpdate: wheel-download world store; MultiServer:
               CommandProcessor without the server/sqlalchemy payload)
    vendor/  — mwgg_gui + the vendored monorepo slice + data assets
               (assembled by sync_vendor.py; doubles as local_path() root)
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SHIMS = os.path.join(APP_DIR, "shims")
VENDOR = os.path.join(APP_DIR, "vendor")
sys.path.insert(0, VENDOR)
sys.path.insert(0, SHIMS)

# Shell selection must precede any mwgg_gui import (bootstrap dispatches on it).
os.environ["MWGG_SHELL"] = "mobile"
os.environ["MWGG_FRONTEND"] = "gui"
os.environ["KIVY_NO_ARGS"] = "1"
# Route world installs through the "worlds venv" path layout: worlds/__init__
# extends its __path__ with mwgg_venv_site_packages("worlds"), which is where
# the ModuleUpdate shim extracts downloaded world wheels.
os.environ["MWGG_USE_WORLDS_VENV"] = "1"

import BaseUtils  # noqa: E402

# Downloaded world wheels (payload + dist-info) land here; on sys.path so
# importlib.metadata sees them as proper installed distributions.
_world_site = BaseUtils.mwgg_venv_site_packages()
os.makedirs(_world_site, exist_ok=True)
if _world_site not in sys.path:
    sys.path.append(_world_site)

# Pin the install root explicitly rather than trusting BaseUtils' __file__
# heuristic (correct here, but load-bearing: data/, LICENSE, QOTD live there).
BaseUtils.local_path.cached_path = VENDOR
# Keep runtime artifacts (logs, host.yaml, downloaded worlds) out of the
# vendor tree; write_path() resolves inside the app sandbox on Android/iOS
# because HOME points there.
BaseUtils.user_path.cached_path = BaseUtils.write_path("user")
os.makedirs(BaseUtils.user_path.cached_path, exist_ok=True)


def _ensure_writable_kivy_data(src: str) -> str:
    """Mirror the bundled Kivy data dir into writable storage and return it.

    Same contract as MultiWorld._ensure_writable_kivy_data: the theme system
    recolors defaulttheme-0.png in place, so KIVY_DATA_DIR must be writable;
    re-sync whenever the bundled copy is newer than the mirror.
    """
    import shutil
    dst = BaseUtils.write_path("kivy", "data")
    marker = "defaulttheme-0.png"
    src_marker = os.path.join(src, "images", marker)
    if not os.path.isfile(src_marker):
        src_marker = os.path.join(src, marker)
    dst_marker = os.path.join(dst, os.path.relpath(src_marker, src))
    needs_copy = not os.path.exists(dst_marker) or (
        os.path.exists(src_marker)
        and os.path.getmtime(src_marker) > os.path.getmtime(dst_marker)
    )
    if needs_copy:
        os.makedirs(dst, exist_ok=True)
        for root, _dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            dst_root = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(dst_root, exist_ok=True)
            for name in files:
                try:
                    shutil.copy2(os.path.join(root, name), os.path.join(dst_root, name))
                except PermissionError:
                    pass
    return dst


os.environ["KIVY_DATA_DIR"] = _ensure_writable_kivy_data(os.path.join(VENDOR, "kivy_data"))
os.environ["KIVY_HOME"] = BaseUtils.write_path("data")
os.makedirs(os.environ["KIVY_HOME"], exist_ok=True)

# Bundled OpenSSL has no system cert store on device; point every default
# SSL context (websockets, requests, kivy loaders) at certifi's bundle.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass


def main() -> None:
    import asyncio
    import logging

    BaseUtils.init_logging("Mobile", "info", show_logo=False)
    logger = logging.getLogger("Mobile")

    async def run() -> None:
        from CommonClient import InitContext

        ctx = InitContext()
        try:
            ctx.run_gui()
            await ctx.exit_event.wait()
        except Exception:
            logger.exception("Error during GUI execution")
        finally:
            try:
                await ctx.shutdown()
            except Exception:
                logger.exception("Error during shutdown")

    asyncio.run(run())


if __name__ == "__main__":
    main()
