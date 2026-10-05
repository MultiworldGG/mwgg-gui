from __future__ import annotations

import os
import sys

# kivy.core modules apply Config at import time (core.text registers the
# default font, core.window sizes/styles the window), so these must be set
# before ANY kivy.core import below. Setting them later only reaches the
# persisted file, which left every fresh KIVY_HOME's first boot rendering
# with vanilla Kivy defaults (Roboto, 800x600, no custom titlebar).
from kivy.config import Config as MWKVConfig

# Forced every boot: a stale config.ini must not break the window.
for section, values in {
    "input": {"mouse": "mouse,disable_multitouch"},
    "kivy": {
        "exit_on_escape": "0",
        "default_font": ['Inter',
                         os.path.join("data", "fonts", "Inter-Regular.ttf"),
                         os.path.join("data", "fonts", "Inter-Italic.ttf"),
                         os.path.join("data", "fonts", "Inter-Bold.ttf"),
                         os.path.join("data", "fonts", "Inter-BoldItalic.ttf")],
        "desktop": "1",
        "pause_on_minimize": "0",
    },
    "graphics": {
        "width": "1099",
        "height": "699",
        # custom_titlebar only works on Windows.
        "custom_titlebar": "1" if sys.platform == "win32" else "0",
        "minimum_height": "480",
        "minimum_width": "400",
        "focus": "False",
        "resizable": "1",
        "borderless": "0",
        "window_state": "visible",
        "position": "auto",
        "rotation": "0",
        "shaped": "0",
        "show_taskbar_icon": "1",
        "show_cursor": "1",
        # User-owned; normalized for getboolean() in the settings switch.
        "fullscreen": "1" if MWKVConfig.get("graphics", "fullscreen") == "1" else "0",
    },
}.items():
    for key, value in values.items():
        MWKVConfig.set(section, key, value)
# Importing kivy already ran Modules.configure(); undo the screen module's env overrides.
if MWKVConfig.has_option("modules", "screen"):
    os.environ.pop("KIVY_METRICS_DENSITY", None)
    os.environ.pop("KIVY_DPI", None)
MWKVConfig.remove_section("modules")
MWKVConfig.adddefaultsection("modules")
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