"""
One INFO line on frame pacing for user logs; Kivy logs the swap interval only
at DEBUG. Read-only: changes no settings.
"""
from __future__ import annotations

__all__ = ("schedule_frame_pacing_log",)

import ctypes
from functools import partial

from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.logger import Logger

from mwgg_gui.components.layout_mode import _loaded_sdl


class _DisplayMode(ctypes.Structure):
    _fields_ = [
        ("format", ctypes.c_uint32),
        ("w", ctypes.c_int),
        ("h", ctypes.c_int),
        ("refresh_rate", ctypes.c_int),
        ("driverdata", ctypes.c_void_p),
    ]


def _sdl_pacing() -> tuple[int | str, int | str]:
    """(effective swap interval, refresh rate of the GL window's display);
    "?" where SDL cannot say. The rate is whole Hz (59.997 reads as 60)."""
    try:
        sdl = _loaded_sdl()
        sdl.SDL_GL_GetCurrentWindow.restype = ctypes.c_void_p
        sdl.SDL_GetWindowDisplayIndex.argtypes = (ctypes.c_void_p,)
        mode = _DisplayMode()
        failed = sdl.SDL_GetCurrentDisplayMode(
            sdl.SDL_GetWindowDisplayIndex(sdl.SDL_GL_GetCurrentWindow()), ctypes.byref(mode))
        return sdl.SDL_GL_GetSwapInterval(), "?" if failed else mode.refresh_rate
    except Exception:
        return "?", "?"


def schedule_frame_pacing_log(at: float = 10, span: float = 2) -> None:
    """Log frame pacing once, `at` s from now, with flips counted over the
    `span` s before it. Clock fps counts loop passes, flips/s counts swaps.
    The window must clear the ~4.5 s of launcher startup stalls after on_start."""
    flips = 0

    def count(*_):
        nonlocal flips
        flips += 1

    def report(start, _dt):
        Window.unbind(on_flip=count)
        interval, refresh = _sdl_pacing()
        Logger.info(
            "FramePacing: swap interval %s, display %s Hz, vsync %r, maxfps %s, "
            "clock %.1f fps, %.1f flips/s",
            interval, refresh, Config.get("graphics", "vsync"), Config.get("graphics", "maxfps"),
            Clock.get_fps(), flips / (Clock.get_time() - start))

    def begin(_dt):
        Window.bind(on_flip=count)
        Clock.schedule_once(partial(report, Clock.get_time()), span)

    Clock.schedule_once(begin, at - span)
