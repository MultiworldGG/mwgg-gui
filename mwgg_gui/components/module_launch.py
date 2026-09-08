from __future__ import annotations
"""
Frontend side of a routed module launch (MultiWorld._route_module_when_ui_ready).

The core feature-detects `before_module_launch` and `on_module_launch_failed`
on the frontend; the copy and policy behind both live here, Kivy-free.
"""
__all__ = (
    "launch_status_lines",
    "LaunchFailureDialog",
    "launch_failure_dialog",
    "launcher_env",
    "spawn_launcher",
)

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

# Set on a client process by MultiWorld.py / BaseUtils.spawn_client; a launcher
# it spawns must start clean (MWGG_ROLE is reassigned there, the rest are read as-is).
_CLIENT_ENV_KEYS = ("MWGG_ROLE", "MWGG_GAME", "MWGG_CLIENT_TYPE", "MWGG_SKIP_UPDATE")


def launch_status_lines(module_name: str, patch_file: str | None = None,
                        **_launch_kwargs) -> list[str]:
    """Loading-overlay lines for a routed launch; empty when there is nothing to announce."""
    if not patch_file:
        return []
    return [f"Patching {os.path.basename(patch_file)}...",
            "A file picker may open for the base ROM or game files the patch needs."]


@dataclass(frozen=True)
class LaunchFailureDialog:
    title: str
    message: str
    ok_text: str
    cancel_text: str | None
    # The OK button opens a fresh launcher; otherwise it exits.
    opens_launcher: bool


def launch_failure_dialog(game_name: str, spawned_by_launcher: bool) -> LaunchFailureDialog:
    """Copy and buttons for the launch-failure box. A launcher-spawned client only
    offers Exit (its launcher is the way back); a standalone one (double-clicked
    patch, CLI) can open a fresh launcher instead."""
    message = f"The {game_name} client could not be started. Details are in the logs folder."
    if spawned_by_launcher:
        return LaunchFailureDialog("Launch Failed", message, "Exit", None, opens_launcher=False)
    return LaunchFailureDialog("Launch Failed", message, "Open Launcher", "Exit", opens_launcher=True)


def launcher_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in environ.items() if key not in _CLIENT_ENV_KEYS}


def spawn_launcher() -> subprocess.Popen:
    """Start a detached launcher process from the shared client entry point."""
    from BaseUtils import get_client_exe, _detached_popen_kwargs
    return subprocess.Popen(list(get_client_exe()), env=launcher_env(os.environ),
                            **_detached_popen_kwargs())
