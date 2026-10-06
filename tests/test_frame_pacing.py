"""Frame pacing log line (components/frame_pacing.py).

frame_pacing.py imports Kivy, flip_sync and layout_mode at module level, so it
is loaded by file path with those imports stubbed; the tests drive the
scheduled callbacks by hand.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "frame_pacing.py"


class _Clock:
    def __init__(self):
        self.time = 0.0
        self.scheduled = []

    def schedule_once(self, callback, timeout):
        self.scheduled.append((callback, timeout))

    def get_time(self):
        return self.time

    def get_fps(self):
        return 77.0

    def run(self, time):
        """Advance to `time` and fire the oldest scheduled callback."""
        self.time = time
        callback, _ = self.scheduled.pop(0)
        callback(0)


class _Window:
    def __init__(self):
        self.flip_callbacks = []

    def bind(self, on_flip):
        self.flip_callbacks.append(on_flip)

    def unbind(self, on_flip):
        self.flip_callbacks.remove(on_flip)

    def flip(self, times):
        for _ in range(times):
            for callback in list(self.flip_callbacks):
                callback(self)


class _Logger:
    def __init__(self):
        self.lines = []

    def info(self, msg, *args):
        self.lines.append(msg % args)


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _sdl(refresh_rate=60, swap_interval=1):
    def current_display_mode(index, mode_ref):
        assert index == 0
        mode_ref._obj.refresh_rate = refresh_rate
        return 0

    return types.SimpleNamespace(
        SDL_GL_GetCurrentWindow=lambda: 0x1234,
        SDL_GetWindowDisplayIndex=lambda window: 0 if window == 0x1234 else -1,
        SDL_GetCurrentDisplayMode=current_display_mode,
        SDL_GL_GetSwapInterval=lambda: swap_interval,
    )


@pytest.fixture
def pacing():
    clock, window, logger = _Clock(), _Window(), _Logger()
    graphics = {"vsync": "", "maxfps": "60"}
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.core": _stub("kivy.core"),
        "kivy.clock": _stub("kivy.clock", Clock=clock),
        "kivy.config": _stub(
            "kivy.config", Config=types.SimpleNamespace(get=lambda section, key: graphics[key])),
        "kivy.core.window": _stub("kivy.core.window", Window=window),
        "kivy.logger": _stub("kivy.logger", Logger=logger),
        "mwgg_gui": _stub("mwgg_gui"),
        "mwgg_gui.components": _stub("mwgg_gui.components"),
        "mwgg_gui.components.flip_sync": _stub(
            "mwgg_gui.components.flip_sync", flip_sync_state=lambda: "on"),
        "mwgg_gui.components.layout_mode": _stub(
            "mwgg_gui.components.layout_mode", _loaded_sdl=_sdl),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("frame_pacing_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return types.SimpleNamespace(module=module, clock=clock, window=window, logger=logger)


def test_logs_once_with_flip_rate_over_the_window(pacing):
    pacing.module._loaded_sdl = lambda: _sdl(refresh_rate=144, swap_interval=1)
    pacing.module.schedule_frame_pacing_log(at=10, span=2)
    assert [timeout for _, timeout in pacing.clock.scheduled] == [8]

    pacing.window.flip(500)  # before counting starts
    pacing.clock.run(8.0)
    assert [timeout for _, timeout in pacing.clock.scheduled] == [2]
    pacing.window.flip(150)
    pacing.clock.run(10.5)
    pacing.window.flip(500)  # after the report: unbound

    assert pacing.window.flip_callbacks == []
    assert pacing.clock.scheduled == []
    assert pacing.logger.lines == [
        "FramePacing: swap interval 1, display 144 Hz, vsync '', maxfps 60, "
        "clock 77.0 fps, 60.0 flips/s, flip sync on"
    ]


def test_sdl_failure_logs_unknowns(pacing):
    def no_sdl():
        raise OSError("SDL2 not loaded")

    pacing.module._loaded_sdl = no_sdl
    pacing.module.schedule_frame_pacing_log(at=5, span=1)
    # Read when the line is logged, after install_flip_sync's first flip.
    pacing.module.flip_sync_state = lambda: "unavailable (GL lookup failed: OSError())"
    pacing.clock.run(4.0)
    pacing.window.flip(60)
    pacing.clock.run(5.0)

    assert pacing.logger.lines == [
        "FramePacing: swap interval ?, display ? Hz, vsync '', maxfps 60, "
        "clock 77.0 fps, 60.0 flips/s, flip sync unavailable (GL lookup failed: OSError())"
    ]


def test_idle_window_is_flagged(pacing):
    pacing.module.schedule_frame_pacing_log(at=10, span=2)
    pacing.clock.run(8.0)
    pacing.window.flip(4)
    pacing.clock.run(10.0)

    assert pacing.logger.lines == [
        "FramePacing: swap interval 1, display 60 Hz, vsync '', maxfps 60, "
        "clock 77.0 fps, 2.0 flips/s (too few redraws to judge vsync), flip sync on"
    ]
