from __future__ import annotations

import sys

if sys.platform == "win32":
    # Must run before anything creates or touches the Window: the `.components`
    # import below pulls in kivymd, which imports kivy.core.window (and thereby
    # creates the Window) as a side effect. The process is deliberately
    # DPI-unaware (see the win32 block in app.py), so Windows scales the whole
    # window for us. Kivy's dynamic DPI handling conflicts with that after a
    # display reconnects: it can briefly use a zero density and then enter a
    # resize/layout loop. Keep Kivy's coordinate system at the fixed 96 DPI
    # that a DPI-unaware process expects.
    # Ported from MultiworldGG main kvui.py (4e8effd4e).
    from kivy.core.window import Window
    from kivy.core.window.window_sdl2 import WindowSDL, _WindowsSysDPIWatch

    def _set_fixed_windows_density(self: WindowSDL):
        self._density = 1.
        self.dpi = 96.

    def _ignore_windows_dpi_changes(self: _WindowsSysDPIWatch):
        pass

    WindowSDL._update_density_and_dpi = _set_fixed_windows_density
    Window._update_density_and_dpi()
    if Window._win_dpi_watch is not None:
        Window._win_dpi_watch.stop()
        Window._win_dpi_watch = None
    _WindowsSysDPIWatch.start = _ignore_windows_dpi_changes

from .components import *
from .console import *
from .hint import *
from .launcher import *
from .settings import *
from .overrides import *

from .loadanimlayout import MWGGLoadingLayout

# Importing this module is a side effect: it patches Kivy's ImageLoader to
# recognize `ap:` and `ap:zip:` URL prefixes used by world client kvs
# (Universal Tracker, etc.). Lives under `overrides/` alongside the other
# kivy/kivymd extension points (screen, expansionlist, markuptextfield, ...).
from .overrides.imageloader import ApAsyncImage, register_url_scheme  # noqa: F401

from .constants import (
    ROLE_LAUNCHER,
    ROLE_CLIENT,
    CONSOLE_ACTIONS,
    LAUNCHER_ACTIONS,
)