from __future__ import annotations
"""Desktop shortcuts that boot a client directly, skipping the launcher.

Windows writes the .lnk itself: pyshortcuts splits its command string at the
first space, which breaks exe paths under directories with spaces. POSIX goes
through pyshortcuts, the same shape as upstream MultiworldGG-Main's Launcher.

Core-only imports (BaseUtils, pyshortcuts) stay function-local so the module
loads import-light for tests.
"""

import os
import subprocess

__all__ = ("client_shortcut_command", "create_client_shortcut")


def client_shortcut_command(game_module: str | None, client_type: str) -> list[str]:
    """The direct-launch argv: BaseUtils.spawn_client's flag contract minus
    the per-session server/slot/password -- a persistent shortcut must not
    bake those in; the spawned client falls back to its persisted defaults.
    """
    from BaseUtils import get_client_exe
    if "APPIMAGE" in os.environ:
        # Only the AppImage itself is launchable from outside its mount.
        argv = [os.environ["ARGV0"]]
    else:
        argv = list(get_client_exe())
    if game_module:
        argv += ["--game", game_module]
    argv += ["--client-type", client_type]
    return argv


def create_client_shortcut(name: str, game_module: str | None, client_type: str) -> None:
    from BaseUtils import is_frozen, is_windows, local_path

    command = client_shortcut_command(game_module, client_type)
    icon = local_path("data", "icon.ico")
    working_dir = None if "APPIMAGE" in os.environ else local_path()
    if is_windows:
        _write_windows_lnk(name, command, working_dir, icon)
        return
    from pyshortcuts import make_shortcut
    if not is_frozen() and "APPIMAGE" not in os.environ:
        # pyshortcuts prepends its own interpreter to a .py script.
        command = command[1:]
    make_shortcut(" ".join(command), name=name, icon=icon, startmenu=False,
                  terminal=False, working_dir=working_dir, noexe=is_frozen())


def _write_windows_lnk(name: str, command: list[str], working_dir: str, icon: str) -> None:
    import win32com.client
    from pyshortcuts import get_folders
    from pyshortcuts.utils import fix_filename

    dest = os.path.join(get_folders().desktop,
                        f"{fix_filename(name, allow_spaces=True)}.lnk")
    shell = win32com.client.Dispatch("WScript.Shell")
    link = shell.CreateShortCut(dest)
    link.Targetpath = command[0]
    link.Arguments = subprocess.list2cmdline(command[1:])
    link.WorkingDirectory = working_dir
    link.Description = name
    if os.path.exists(icon):
        link.IconLocation = icon
    link.save()
