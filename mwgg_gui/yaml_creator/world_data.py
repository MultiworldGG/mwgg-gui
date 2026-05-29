"""
Client for the out-of-process worker that extracts option metadata for
a world.

The GUI must not import worlds itself (`AutoWorldRegister` is a global
that pulls in lots of state), so all option introspection happens in
the subprocess defined in `worker.py`. This module spawns that
subprocess, feeds it a JSON request over stdin, and parses the JSON
response from stdout.

The worker never installs anything: if the world isn't already
importable, the worker exits with code `_EXIT_NEEDS_INSTALL` and a
`needs_install` payload, and we install via `Utils.set_game_names`
here in the GUI process before relaunching the worker once.

Public API:
    load_world_data(game_name, visibility="simple") -> dict
    WorldDataError — raised on worker failure or unparseable response
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from BaseUtils import local_path, is_frozen, mwgg_venv_python

logger = logging.getLogger("Client")

__all__ = ("WorldDataError", "load_world_data")

# The worker script lives in MultiworldGG's `data/` dir, not next to this
# file. That sidesteps the cx_Freeze packaging headaches around bundling a
# subprocess-only .py: data/ is shipped wholesale via setup.py's
# `include_files`, so the file is automatically present in every install
# shape (dev tree, tarball, AppImage). Same place data/mods/multiworld.py
# and data/lua/*.lua live for the same reason.
_WORKER_PATH = Path(local_path("data", "yaml_worker.py"))

# Worker timeout. The worker no longer installs anything, so 60s is plenty
# even with slow disks.
_TIMEOUT_SECONDS = 60

# Exit code the worker uses to signal "world isn't installed; please install
# and relaunch me". Mirrored in data/yaml_worker.py.
_EXIT_NEEDS_INSTALL = 2


class WorldDataError(Exception):
    """Worker failed, timed out, or returned an unparseable response.

    `message` is safe to show in the UI; `trace` (if present) is the
    worker-side Python traceback for the log.
    """

    def __init__(self, message: str, trace: Optional[str] = None):
        super().__init__(message)
        self.trace = trace


def _run_worker(game_name: str, visibility: str) -> subprocess.CompletedProcess:
    """Spawn the yaml worker once and return the CompletedProcess.

    Raises WorldDataError on timeout / spawn failure; otherwise returns the
    process result so the caller can inspect returncode + stdout payload.
    """
    request = json.dumps({"game_name": game_name, "visibility": visibility})

    # The worker needs the MultiworldGG repo on its path so it can
    # `import Utils, Options, worlds` etc. Use `local_path()` to find
    # it the same way the rest of the app does.
    mwgg_root = local_path()
    # In frozen (cx_Freeze) builds, top-level modules like Utils/BaseUtils/
    # Options live inside lib/library.zip (zip_include_packages="*"), and
    # extracted packages like worlds/mwgg_gui live under lib/. The cx_Freeze
    # launcher wires both onto its own sys.path automatically, but a separately
    # spawned venv Python has no idea — without these entries it fails with
    # `ModuleNotFoundError: No module named 'Utils'`.
    path_entries = [mwgg_root]
    if is_frozen():
        path_entries.extend([
            os.path.join(mwgg_root, "lib", "library.zip"),
            os.path.join(mwgg_root, "lib"),
        ])
    env = os.environ.copy()
    # Prepend our entries to PYTHONPATH (don't overwrite — leave the
    # user's pre-existing entries intact).
    existing = env.get("PYTHONPATH", "")
    new_pythonpath = os.pathsep.join(path_entries)
    env["PYTHONPATH"] = (
        f"{new_pythonpath}{os.pathsep}{existing}" if existing else new_pythonpath
    )
    # The worker is run by mwgg_venv's vanilla Python, so it has no `sys.frozen`
    # and `BaseUtils.local_path()` mis-resolves (it falls through to
    # `__main__.__file__`, landing in <root>/data instead of <root>). Pass the
    # bundle root so the worker can prime sys.frozen + sys.argv[0] before any
    # BaseUtils import triggers cached_path setup.
    if is_frozen():
        env["MWGG_FROZEN_BUNDLE_ROOT"] = mwgg_root
    # Suppress Kivy's own argument parser, mirroring Generate.py spawning.
    env["KIVY_NO_ARGS"] = "1"

    # In frozen builds, sys.executable is the cx_Freeze MultiWorldGG launcher,
    # not a Python interpreter — passing a `.py` script to it hits
    # MultiWorld.py's argparse and dies with "unrecognized arguments". Use the
    # mwgg_venv's real Python instead (the same interpreter ModuleUpdate uses
    # for `pip list --python …`). Dev runs keep using sys.executable.
    python_exe = mwgg_venv_python() if is_frozen() else sys.executable
    cmd = [python_exe, str(_WORKER_PATH)]
    logger.debug("yaml-worker spawn: %s (cwd=%s)", cmd, mwgg_root)

    try:
        return subprocess.run(
            cmd,
            input=request,
            capture_output=True,
            text=True,
            env=env,
            cwd=mwgg_root,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise WorldDataError(
            f"Timed out after {_TIMEOUT_SECONDS}s loading options for {game_name}."
        )
    except OSError as e:
        raise WorldDataError(f"Could not spawn yaml worker: {e}")


def _parse_payload(result: subprocess.CompletedProcess) -> dict:
    """Parse the worker's stdout JSON, or raise WorldDataError on garbage."""
    stdout = result.stdout.strip()
    if not stdout:
        raise WorldDataError("Worker returned no output.", trace=result.stderr)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        # The worker might have crashed mid-write or printed extra
        # noise. Try to recover the last JSON line.
        last_line = stdout.splitlines()[-1] if stdout.splitlines() else ""
        try:
            return json.loads(last_line)
        except json.JSONDecodeError:
            raise WorldDataError(
                f"Could not parse worker response: {e}",
                trace=stdout[-2000:],
            )


def _install_world(slug: str) -> None:
    """Install a missing world by slug via ModuleUpdate.install_worlds.

    Calling install_worlds directly (rather than Utils.set_game_names) keeps
    `import worlds` out of the GUI process — the re-spawned worker stays the
    sole AutoWorldRegister consumer. install_worlds resolves the wheel URL
    from mwgg_igdb and pip-installs via uv; the worker re-probes on relaunch.
    """
    logger.info("Installing world '%s' via ModuleUpdate.install_worlds", slug)
    import ModuleUpdate
    ModuleUpdate.install_worlds([slug])


def load_world_data(game_name: str, visibility: str = "simple") -> dict:
    """Invoke the worker and return the parsed JSON response.

    If the worker reports the world isn't installed, install it via
    Utils.set_game_names and relaunch the worker once. Raises WorldDataError
    on any other failure or if the install retry still can't find the world.
    """
    install_attempted = False
    while True:
        result = _run_worker(game_name, visibility)

        if result.returncode == _EXIT_NEEDS_INSTALL:
            payload = _parse_payload(result)
            slug = payload.get("needs_install")
            if not slug:
                raise WorldDataError(
                    f"Worker signalled needs_install with no slug: {payload!r}",
                    trace=result.stderr,
                )
            if install_attempted:
                raise WorldDataError(
                    f"Install of '{game_name}' did not produce an importable "
                    f"world. Check the parent app's log for the install output.",
                    trace=result.stderr,
                )
            _install_world(slug)
            install_attempted = True
            continue

        if result.returncode != 0:
            raise WorldDataError(
                f"Worker exited with code {result.returncode}: {result.stderr.strip()[:400]}",
                trace=result.stderr,
            )

        payload = _parse_payload(result)
        if not payload.get("ok"):
            # Fall back to the captured stderr if the worker didn't include a
            # trace of its own — the underlying logging.warning from
            # WorldSource.load ends up there and is usually what we want to
            # see in the GUI log.
            raise WorldDataError(
                payload.get("error", "Worker reported failure"),
                trace=payload.get("trace") or (result.stderr or None),
            )

        return payload
