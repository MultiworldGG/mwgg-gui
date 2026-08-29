"""
Out-of-process client for MultiworldGG's `Generate` JSON modes.

The GUI must not import game worlds into its own interpreter
(`AutoWorldRegister` pulls in a lot of global state), so option introspection
(`--yaml-options`) and datapackage export (`--export-datapackage`) run in a
separate `Generate` process. The argv prefix is resolved through
`LauncherComponents.get_exe`, which reads `BaseUtils.FROZEN_TARGETS`
(the single source of truth for built exe names), so this module can't
drift from the actual frozen executable. LauncherComponents is a top-level
core module: importing it never touches the `worlds` package, so no world
code runs in this interpreter.

Generate installs the worlds if needed, loads them, and writes a single JSON
object to stdout. All of its own logging/noise is diverted to stderr in these
modes, so stdout carries only the payload.

Public API:
    load_world_data(game_name, visibility="simple") -> dict
    run_generate_json(args, timeout=...) -> dict
    WorldDataError - raised on subprocess failure or unparseable response
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional

from BaseUtils import is_frozen, is_windows

logger = logging.getLogger("Client")

__all__ = ("WorldDataError", "load_world_data", "run_generate_json")

# Generous: a first call for a missing world includes a uv install (slow on cold cache).
_TIMEOUT_SECONDS = 300

# A world can't load in the process that just installed it; on this exit code
# re-run Generate once (mirrors Generate.EXIT_NEEDS_RELOAD).
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
    """Build the argv prefix that runs MultiworldGG's Generate entry point.

    Resolved through LauncherComponents (same path as the launcher's own
    generation flow) so the frozen exe name can't drift from
    BaseUtils.FROZEN_TARGETS. The function-local import keeps world_data
    loadable standalone.
    """
    from LauncherComponents import find_component, get_exe

    component = find_component("Generate")
    if component is None:
        raise WorldDataError("No 'Generate' component is registered.")
    cmd = get_exe(component)
    if cmd is None:
        raise WorldDataError("Could not resolve the Generate executable.")
    return cmd


def _run_generate(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Spawn Generate once with `args`. Raises WorldDataError on timeout /
    spawn failure; otherwise returns the CompletedProcess for the caller to
    inspect (returncode + stdout)."""
    prefix = _generate_command()
    cmd = prefix + list(args)
    # get_settings() prefers a host.yaml in cwd; run at the exe's dir (parity with launcher.py).
    cwd = os.path.dirname(prefix[-1])
    env = os.environ.copy()
    # Gates ModuleUpdate.update(): a frozen child would otherwise
    # respawn a detached duplicate Generate console and exit 10.
    env["SKIP_REQUIREMENTS_UPDATE"] = "1"
    # Keep the child's piped output UTF-8 regardless of locale.
    env["PYTHONIOENCODING"] = "utf-8"
    if not is_frozen():
        # Disable Kivy's argument parser when running from source.
        env["KIVY_NO_ARGS"] = "1"
    kwargs = {}
    if is_windows:
        # Console-subsystem exe: without this every fetch flashes a console window.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    logger.debug("yaml-options spawn: %s", cmd)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env=env,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        raise WorldDataError(f"Timed out after {timeout}s running Generate {args[0]}.")
    except OSError as e:
        raise WorldDataError(f"Could not run Generate: {e}")


def run_generate_json(args: list[str], timeout: int = _TIMEOUT_SECONDS) -> dict:
    """Run `Generate *args` and return the parsed JSON payload from its stdout.

    If Generate had to install a world it exits `_EXIT_NEEDS_RELOAD`; we re-run
    it once so the freshly-installed world loads in a clean process. Raises
    `WorldDataError` if the subprocess fails, its output can't be parsed, or
    the payload reports `ok: false`.
    """
    result = _run_generate(args, timeout)
    if result.returncode == _EXIT_NEEDS_RELOAD:
        logger.info(
            "Generate requested reload (world installed or environment "
            "refreshed); re-running once."
        )
        result = _run_generate(args, timeout)

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


def load_world_data(game_name: str, visibility: str = "simple", module: str = "") -> dict:
    """Option metadata for `game_name` via `--yaml-options`. `module` is the
    world's module slug; passing it lets custom (non-pip) worlds load without
    a game-index lookup."""
    args = ["--yaml-options", "--game", game_name, "--visibility", visibility]
    if module:
        args += ["--module", module]
    return run_generate_json(args)
