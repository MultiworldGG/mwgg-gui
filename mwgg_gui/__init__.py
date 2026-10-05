from __future__ import annotations

import os
import sys

# kivy.core modules apply Config at import time (core.text registers the
# default font, core.window sizes/styles the window), so these must be set
# before ANY kivy.core import below. Setting them later only reaches the
# persisted file, which left every fresh KIVY_HOME's first boot rendering
# with vanilla Kivy defaults (Roboto, 800x600, no custom titlebar).
from kivy.config import Config as MWKVConfig

MWKVConfig.set("input", "mouse", "mouse,disable_multitouch")
MWKVConfig.set("kivy", "exit_on_escape", "0")
MWKVConfig.set("kivy", "default_font", ['Inter',
                                        os.path.join("data", "fonts", "Inter-Regular.ttf"),
                                        os.path.join("data", "fonts", "Inter-Italic.ttf"),
                                        os.path.join("data", "fonts", "Inter-Bold.ttf"),
                                        os.path.join("data", "fonts", "Inter-BoldItalic.ttf")])
MWKVConfig.set("graphics", "width", "1099")
MWKVConfig.set("graphics", "height", "699")
# custom_titlebar only works on Windows; write "0" elsewhere to overwrite a
# value persisted to KIVY_HOME by a previous Windows run.
MWKVConfig.set("graphics", "custom_titlebar", "1" if sys.platform == "win32" else "0")
MWKVConfig.set("graphics", "minimum_height", "700")
MWKVConfig.set("graphics", "minimum_width", "600")
MWKVConfig.set("graphics", "focus", "False")
MWKVConfig.write()

if sys.platform == "win32":
    # Per-monitor-v2 aware with SDL scaling off, so SDL window, mouse and
    # hit-test coordinates are GL pixels. Must precede the Window import; the
    # env var outranks Kivy's SDL hint. Awareness is set by call, not by
    # SDL_WINDOWS_DPI_AWARENESS, which child SDL processes would inherit.
    from ctypes import c_void_p, windll

    os.environ["SDL_WINDOWS_DPI_SCALING"] = "0"
    try:
        windll.user32.SetProcessDpiAwarenessContext(c_void_p(-4))
    except AttributeError:  # before Windows 10 1703
        pass
    else:
        # SDL centres the window at its creation size, which is now in pixels.
        scale = windll.user32.GetDpiForSystem() / 96
        for key in ("width", "height"):
            MWKVConfig.set("graphics", key, str(round(MWKVConfig.getint("graphics", key) * scale)))

    from kivy.core.window import Window
    from kivy.core.window.window_sdl2 import WindowSDL, _WindowsSysDPIWatch

    def _set_fixed_windows_density(self: WindowSDL):
        self._density = 1.

    def _ignore_windows_dpi_changes(self: _WindowsSysDPIWatch):
        pass

    WindowSDL._update_density_and_dpi = _set_fixed_windows_density
    Window._update_density_and_dpi()
    # dp()/sp() and KivyMD font styles bake at creation: set dpi once, before
    # kivymd imports, and never rescale per monitor.
    try:
        Window.dpi = float(windll.user32.GetDpiForWindow(Window._win.get_window_info().window) or 96)
    except AttributeError:  # before Windows 10 1607
        Window.dpi = 96.
    if Window._win_dpi_watch is not None:
        Window._win_dpi_watch.stop()
        Window._win_dpi_watch = None
    _WindowsSysDPIWatch.start = _ignore_windows_dpi_changes

    from kivy.metrics import dp

    # The titlebar hit-test border is in physical pixels.
    MWKVConfig.set("graphics", "custom_titlebar_border", str(round(dp(5))))

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
    TEXT_INPUT_ACTIONS,
)