"""
Client for the out-of-process worker that extracts option metadata for
a world.

The GUI must not import worlds itself (`AutoWorldRegister` is a global
that pulls in lots of state), so all option introspection happens in
the subprocess defined in `worker.py`. This module spawns that
subprocess, feeds it a JSON request over stdin, and parses the JSON
response from stdout.

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

from BaseUtils import local_path

logger = logging.getLogger("Client")

__all__ = ("WorldDataError", "load_world_data")

_WORKER_PATH = Path(__file__).with_name("worker.py")

# How long to give the worker. First call for a missing world includes
# a pip install which can take a while on slow connections.
_TIMEOUT_SECONDS = 300


class WorldDataError(Exception):
    """Worker failed, timed out, or returned an unparseable response.

    `message` is safe to show in the UI; `trace` (if present) is the
    worker-side Python traceback for the log.
    """

    def __init__(self, message: str, trace: Optional[str] = None):
        super().__init__(message)
        self.trace = trace


def load_world_data(game_name: str, visibility: str = "simple") -> dict:
    """Invoke the worker and return the parsed JSON response.

    Raises `WorldDataError` if the worker fails.
    """
    request = json.dumps({"game_name": game_name, "visibility": visibility})

    # The worker needs the MultiworldGG repo on its path so it can
    # `import Utils, Options, worlds` etc. Use `local_path()` to find
    # it the same way the rest of the app does.
    mwgg_root = local_path()
    env = os.environ.copy()
    # Prepend mwgg_root to PYTHONPATH (don't overwrite — leave the
    # user's pre-existing entries intact).
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{mwgg_root}{os.pathsep}{existing}" if existing else mwgg_root
    )
    # Suppress Kivy's own argument parser, mirroring Generate.py spawning.
    env["KIVY_NO_ARGS"] = "1"

    cmd = [sys.executable, str(_WORKER_PATH)]
    logger.debug("yaml-worker spawn: %s (cwd=%s)", cmd, mwgg_root)

    try:
        result = subprocess.run(
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

    if result.returncode != 0:
        raise WorldDataError(
            f"Worker exited with code {result.returncode}: {result.stderr.strip()[:400]}",
            trace=result.stderr,
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise WorldDataError("Worker returned no output.", trace=result.stderr)

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        # The worker might have crashed mid-write or printed extra
        # noise. Try to recover the last JSON line.
        last_line = stdout.splitlines()[-1] if stdout.splitlines() else ""
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError:
            raise WorldDataError(
                f"Could not parse worker response: {e}",
                trace=stdout[-2000:],
            )

    if not payload.get("ok"):
        raise WorldDataError(
            payload.get("error", "Worker reported failure"),
            trace=payload.get("trace"),
        )

    return payload
