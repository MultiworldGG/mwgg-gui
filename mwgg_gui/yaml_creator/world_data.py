"""
Client for extracting a world's option metadata out-of-process.

The GUI must not import game worlds into its own interpreter
(`AutoWorldRegister` pulls in a lot of global state), so option introspection
runs in a separate process: we invoke MultiworldGG's `Generate` entry point
with `--yaml-options`. The argv prefix is resolved through
`LauncherComponents.get_exe`, which reads `BaseUtils.FROZEN_TARGETS`
— the single source of truth for built exe names — so this module can't
drift from the actual frozen executable. LauncherComponents is a top-level
core module: importing it never touches the `worlds` package, so no world
code runs in this interpreter.

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
from typing import Optional

from BaseUtils import is_frozen, is_windows

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
    """Build the argv prefix that runs MultiworldGG's Generate entry point.

    Resolved through LauncherComponents — same path as the launcher's own
    generation flow — so the frozen exe name can't drift from the actual
    built target (see BaseUtils.FROZEN_TARGETS). The import stays inside
    the function: keeping it off the module import path keeps world_data
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


def _run_generate(game_name: str, visibility: str, module: str = "") -> subprocess.CompletedProcess:
    """Spawn Generate --yaml-options once. Raises WorldDataError on timeout /
    spawn failure; otherwise returns the CompletedProcess for the caller to
    inspect (returncode + stdout)."""
    prefix = _generate_command()
    cmd = prefix + [
        "--yaml-options",
        "--game", game_name,
        "--visibility", visibility,
    ]
    # Pass the module slug so a custom (non-pip) world loads without a game-index
    # lookup — the index in a fresh Generate process only knows pip/index worlds.
    if module:
        cmd += ["--module", module]
    # Run at the exe's directory: the child's get_settings() prefers a
    # host.yaml in cwd over the user_path one, and the launcher process's
    # own cwd is arbitrary. Parity with the generation flow in launcher.py.
    cwd = os.path.dirname(prefix[-1])
    env = os.environ.copy()
    # Block ModuleUpdate's self-update path in the child: on frozen builds
    # Utils.exit_restart_for_update would respawn a detached duplicate
    # Generate in a new console and exit 10. dump_yaml_options' world-install
    # path is unaffected — only ModuleUpdate.update() is gated by this.
    env["SKIP_REQUIREMENTS_UPDATE"] = "1"
    if not is_frozen():
        # Disable Kivy's argument parser when running from source.
        env["KIVY_NO_ARGS"] = "1"
    kwargs = {}
    if is_windows:
        # Generate is a console-subsystem exe; without this every options
        # fetch flashes a console window on frozen Windows.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    logger.debug("yaml-options spawn: %s", cmd)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
            env=env,
            **kwargs,
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
    """
    result = _run_generate(game_name, visibility, module)
    if result.returncode == _EXIT_NEEDS_RELOAD:
        logger.info(
            "Generate requested reload (world installed or environment "
            "refreshed); re-running once."
        )
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
