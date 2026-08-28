from __future__ import annotations

import sys

if sys.platform == "win32":
    # Must run before the imports below pull in kivymd and create the Window.
    # The process is deliberately DPI-unaware (see app.py's win32 block); pin
    # Kivy at 96 DPI, since after a display reconnect its dynamic DPI handling
    # can hit a zero density and enter a resize/layout loop.
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

# Side-effect import: patches Kivy's ImageLoader to recognize the `ap:` and
# `ap:zip:` URL prefixes used by world client kvs.
from .overrides.imageloader import ApAsyncImage, register_url_scheme  # noqa: F401

from .constants import (
    ROLE_LAUNCHER,
    ROLE_CLIENT,
    CONSOLE_ACTIONS,
    LAUNCHER_ACTIONS,
)