"""
Launcher Components Helpers
"""
from __future__ import annotations

__all__ = ("LauncherComponentData", "builtin_menu_entries", "world_tool_activator")

import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional

from kivy.clock import Clock

from mwgg_gui.components.dialog import MessageBox, confirm_arbitrary_code

logger = logging.getLogger("Client")


@dataclass
class LauncherComponentData:
    """A data class for a launcher component entry."""
    title: str
    description: str
    activate: Callable[[], None]
    icon_source: Optional[str] = None
    icon_name: Optional[str] = None


def world_tool_activator(run_fn, tool) -> Callable[[], None]:
    """Wrap a world tool/adjuster run behind the arbitrary-code warning with
    the world's own suppression key. Returns a callable that, when invoked,
     will either show the warning or run the tool."""
    def _run():
        try:
            run_fn(tool.module, tool.name)
        except Exception as e:
            logger.exception("World tool %r (%s) failed", tool.name, tool.module)
            Clock.schedule_once(lambda dt, err=e: MessageBox(
                "World Tool",
                f"'{tool.name}' failed: {err}",
                is_error=True,
            ).open())
    #TODO: apworld installs simply copy the world into the custom_worlds directory
    #      we are concerned with other tools that are bundled as .apworlds (for example, a datapackage reader)
    #      we need to give that a child process (preferably with less execution privileges)
    def _start():
        threading.Thread(target=_run, name=f"world-tool-{tool.module}", daemon=True).start()

    #TODO: This is WILDLY unnessary for most cases.  The arbitrary code warning should show only for
    # .apworld custom_worlds that use 'tool' or 'adjuster' components.  Indexed worlds should
    # never see this.
    return partial(
        confirm_arbitrary_code,
        "Run World Tool",
        f"'{tool.name}' is part of the '{tool.world_name}' APWorld. "
        "Running it executes that APWorld's code on your computer with "
        "your permissions. Only continue if you trust where this APWorld "
        "came from.",
        f"tool_warning_ok_{tool.module}",
        _start,
        confirm_text="Run Tool",
    )


# Builtins the play pane already surfaces: Generate and Host have their own
# buttons, Text Client is a client-type radio, Open Patch is the play pane's
# patch button.
_PLAY_PANE_COMPONENTS = frozenset({"Generate", "Host", "Text Client", "Open Patch"})

# Builtins surfaced as topappbar trailing icons rather than menu items.
_APPBAR_ICON_COMPONENTS = frozenset({"MultiworldGG Website", "Unofficial AP Discord"})


def builtin_menu_entries() -> list[LauncherComponentData]:
    """Builtin tool components for the topappbar menu, excluding what the
    play pane already surfaces. The import is a sys.modules hit once the
    launcher's background component scan has run."""
    import worlds.LauncherComponents as launcher_components

    entries: list[LauncherComponentData] = []
    for component in launcher_components.builtin_components():
        if component.type is launcher_components.Type.HIDDEN:
            continue
        if component.display_name in _PLAY_PANE_COMPONENTS | _APPBAR_ICON_COMPONENTS:
            continue
        activate = component.func or partial(launcher_components.run_component, component)
        if component.display_name == "Install APWorld":
            # Wrapped here rather than trusting core's native confirm --
            # core skips its own messagebox path while Kivy is running.
            activate = partial(
                confirm_arbitrary_code,
                "Install APWorld",
                "APWorlds contain program code that runs on your computer "
                "when the world is loaded. Only install APWorlds from "
                "sources you trust.",
                "suppress_apworld_install_warning",
                activate,
                confirm_text="Install",
            )
        entries.append(LauncherComponentData(
            title=component.display_name,
            description=component.description,
            activate=activate,
        ))
    return entries
