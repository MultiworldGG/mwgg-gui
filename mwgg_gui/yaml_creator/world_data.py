"""
Client for extracting a world's option metadata out-of-process.

The GUI must not import worlds into its own interpreter (`AutoWorldRegister`
pulls in a lot of global state), so option introspection runs in a separate
process. We invoke MultiworldGG's `Generate` entry point with `--yaml-options`:
in frozen builds that's the bundled `MultiWorldGGGenerate` executable, which
runs in the full frozen environment (so worlds' C-extension base deps like
bsdiff4 import correctly); in dev it's `python Generate.py`.

Generate installs the world if needed, loads it, and writes a single JSON
object to stdout. All of its own logging/noise is diverted to stderr in this
mode, so stdout carries only the payload.

Public API:
    load_world_data(game_name, visibility="simple") -> dict
    WorldDataError — raised on subprocess failure or unparseable response
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from BaseUtils import local_path, is_frozen, is_windows

logger = logging.getLogger("Client")

__all__ = ("WorldDataError", "load_world_data")

# Generous: the first call for a missing world includes a uv install, which can
# be slow on a cold cache / slow connection.
_TIMEOUT_SECONDS = 300

# Generate exits with this code after installing a previously-missing world: the
# world can't be loaded in the same process that just installed it, so we re-run
# Generate once and the fresh process loads it cleanly. Mirrors
# Generate.EXIT_NEEDS_RELOAD / the project-wide "needs reload" convention.
_EXIT_NEEDS_RELOAD = 10


class WorldDataError(Exception):
    """Subprocess failed, timed out, or returned an unparseable response.

    `message` is safe to show in the UI; `trace` (if present) is diagnostic
    output for the log.
    """

    def __init__(self, message: str, trace: Optional[str] = None):
        super().__init__(message)
        self.trace = trace


def _generate_command() -> list[str]:
    """Build the argv prefix that runs MultiworldGG's Generate entry point."""
    if is_frozen():
        # The Generate executable is a sibling of the running launcher.
        exe_name = "MultiWorldGGGenerate.exe" if is_windows else "MultiWorldGGGenerate"
        exe = Path(sys.executable).parent / exe_name
        return [str(exe)]
    # Dev: run the script with the current interpreter. local_path() resolves to
    # the MultiworldGG repo root, where Generate.py lives.
    return [sys.executable, str(Path(local_path("Generate.py")))]


def _run_generate(game_name: str, visibility: str, module: str = "") -> subprocess.CompletedProcess:
    """Spawn Generate --yaml-options once. Raises WorldDataError on timeout /
    spawn failure; otherwise returns the CompletedProcess for the caller to
    inspect (returncode + stdout)."""
    cmd = _generate_command() + [
        "--yaml-options",
        "--game", game_name,
        "--visibility", visibility,
    ]
    # Pass the module slug so a custom (non-pip) world loads without a game-index
    # lookup — the index in a fresh Generate process only knows pip/index worlds.
    if module:
        cmd += ["--module", module]
    logger.debug("yaml-options spawn: %s", cmd)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise WorldDataError(
            f"Timed out after {_TIMEOUT_SECONDS}s loading options for {game_name}."
        )
    except OSError as e:
        raise WorldDataError(f"Could not run Generate for option metadata: {e}")


def load_world_data(game_name: str, visibility: str = "simple", module: str = "") -> dict:
    """Run Generate --yaml-options for `game_name` and return the parsed JSON.

    `module` is the world's module slug; passing it lets custom (non-pip) worlds
    load without a game-index lookup. If Generate had to install the world it
    exits `_EXIT_NEEDS_RELOAD`; we re-run it once so the freshly-installed world
    loads in a clean process. Raises `WorldDataError` if the subprocess fails or
    its output can't be parsed.

    On mobile there are no subprocesses: the world loads in-process and the
    same payload is built directly (see world_data_mobile.py).
    """
    from mwgg_gui.constants import IS_MOBILE
    if IS_MOBILE:
        from mwgg_gui.yaml_creator.world_data_mobile import load_world_data_in_process
        return load_world_data_in_process(game_name, visibility, module)

    result = _run_generate(game_name, visibility, module)
    if result.returncode == _EXIT_NEEDS_RELOAD:
        logger.info("Generate installed '%s'; re-running to load it.", game_name)
        result = _run_generate(game_name, visibility, module)

    if result.returncode != 0:
        raise WorldDataError(
            f"Generate exited with code {result.returncode}: {result.stderr.strip()[:400]}",
            trace=result.stderr,
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise WorldDataError("Generate returned no output.", trace=result.stderr)

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        # Recover the last JSON line in case anything still leaked onto stdout.
        last_line = stdout.splitlines()[-1] if stdout.splitlines() else ""
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError:
            raise WorldDataError(
                f"Could not parse option metadata: {e}",
                trace=(stdout[-2000:] + "\n--- stderr ---\n" + (result.stderr or "")),
            )

    if not payload.get("ok"):
        raise WorldDataError(
            payload.get("error", "Generate reported failure"),
            trace=payload.get("trace") or (result.stderr or None),
        )

    return payload
