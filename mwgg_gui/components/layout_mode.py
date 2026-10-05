"""
Compact-mode layout service, exposed as ``app.layout_mode``.

Compact Mode is the Settings > Interface > Layout switch: a portrait window
whose screens stack their panes vertically. The launcher rebuilds itself when
the switch flips; clients are separate processes and read the persisted
value at boot. A display too small for the desktop minimum forces it for the
process. The pure helpers stay Kivy-free so the unit tests can load this
module with the Kivy imports stubbed.
"""
from __future__ import annotations

__all__ = ("LayoutMode", "get_layout_mode", "needs_compact", "read_compact_mode", "window_geometry")

import ctypes
import math
import os
import re
import sys

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.event import EventDispatcher
from kivy.metrics import Metrics, dp
from kivy.properties import AliasProperty, BooleanProperty, NumericProperty

# (size, minimum size) per mode, in dp. The desktop values match the historical
# post-splash resize; the compact minimum keeps about three rows in the
# classic hint table.
_WINDOW_GEOMETRY = {
    False: ((1100, 700), (600, 700)),
    True: ((460, 800), (400, 480)),
}


def read_compact_mode(app_config) -> bool:
    """client.compact_mode; a client.ini written by the old switch only
    carries device_orientation=Portrait, which meant the same thing."""
    if app_config.has_option("client", "compact_mode"):
        return app_config.getboolean("client", "compact_mode")
    return app_config.get("client", "device_orientation", fallback="") == "Portrait"


def needs_compact(work_area: tuple[float, float] | None) -> bool:
    """Whether the desktop minimum overflows the work area (dp); an unknown
    work area never forces compact."""
    width, height = _WINDOW_GEOMETRY[False][1]
    return work_area is not None and (work_area[0] < width or work_area[1] < height)


def window_geometry(compact: bool, work_area: tuple[float, float] | None = None
                    ) -> tuple[tuple[float, float], tuple[float, float]]:
    """(window size, minimum window size) for the mode, clipped per axis to
    the work area."""
    area = work_area or (math.inf, math.inf)
    size, minimum = _WINDOW_GEOMETRY[bool(compact)]
    return tuple(map(min, size, area)), tuple(map(min, minimum, area))


def _window_units(value: float) -> int:
    """dp to SDL window units (Windows: pixels, macOS: points)."""
    return round(dp(value) / Window._density)


class _Rect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("x", "y", "w", "h")]


def _loaded_sdl() -> ctypes.CDLL:
    """The SDL2 Kivy already initialised; a second copy would know no displays."""
    if sys.platform == "win32":
        return ctypes.CDLL("SDL2")
    if sys.platform == "darwin":
        dyld = ctypes.CDLL(None)
        dyld._dyld_get_image_name.restype = ctypes.c_char_p
        paths = [os.fsdecode(dyld._dyld_get_image_name(i)) for i in range(dyld._dyld_image_count())]
    else:
        with open("/proc/self/maps") as maps:
            paths = [line.split(maxsplit=5)[-1].strip() for line in maps]
    return ctypes.CDLL(next(
        path for path in paths if re.fullmatch(r"(lib)?SDL2([-.].*)?", os.path.basename(path))))


def _usable_bounds() -> tuple[int, int, int, int] | None:
    """Usable (x, y, w, h) of the window's display in SDL window units, or None."""
    try:
        sdl = _loaded_sdl()
        rect = _Rect(Window.left, Window.top, *Window.system_size)
        if sdl.SDL_GetDisplayUsableBounds(sdl.SDL_GetRectDisplayIndex(ctypes.byref(rect)),
                                          ctypes.byref(rect)):
            return None
    except Exception:
        return None
    # Usable bounds include native title bars; win32 draws its own inside the window.
    title = 0 if sys.platform == "win32" else 28
    return rect.x, rect.y + title, rect.w, rect.h - title


class LayoutMode(EventDispatcher):
    # The Settings switch, persisted as client.compact_mode.
    preferred = BooleanProperty(False)
    # The display cannot fit the desktop minimum; never persisted.
    forced = BooleanProperty(False)
    work_area: tuple[float, float] | None = None
    # Height screens reserve above the bottom bar for the full-width connect
    # bar (components/connect_layout); 0 while it is empty or inside the bar.
    connect_bar_height = NumericProperty(0)

    def _get_compact(self):
        return self.preferred or self.forced

    def _set_compact(self, value):
        self.preferred = value

    compact = AliasProperty(_get_compact, _set_compact, bind=("preferred", "forced"), cache=True)

    def fit_display(self) -> None:
        bounds = _usable_bounds()
        scale = Window._density / Metrics.density
        self.work_area = bounds and (bounds[2] * scale, bounds[3] * scale)
        self.forced = needs_compact(self.work_area)

    def apply_window_geometry(self) -> None:
        size, minimum = window_geometry(self.compact, self.work_area)
        width, height = map(_window_units, size)
        Window.size = width, height
        Window.minimum_width, Window.minimum_height = map(_window_units, minimum)
        # SDL keeps the top-left on resize; the creation size may have left it off-screen.
        bounds = _usable_bounds()
        if bounds:
            x, y, w, h = bounds
            Window.left = max(min(Window.left, x + w - width), x)
            Window.top = max(min(Window.top, y + h - height), y)
        # On win32 Window.width/height read the GL surface, which SDL resizes
        # only after the property observers already ran, so kv bindings on
        # `Window.height` keep the old value; re-dispatch next frame.
        Clock.schedule_once(lambda dt: Window.property("_size").dispatch(Window), 0)


_instance: LayoutMode | None = None


def get_layout_mode() -> LayoutMode:
    """Shared instance, created on first use; every MultiMDApp instance
    (phantom post-takeover ones included) binds to this one object."""
    global _instance
    if _instance is None:
        _instance = LayoutMode()
    return _instance
