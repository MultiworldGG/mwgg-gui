"""Loading animation frame timing (loadanimlayout.py).

loadanimlayout.py imports Kivy and KivyMD at module level, so it is loaded by
file path with those imports stubbed; Clock is a fake whose tick time the
tests drive directly, at the tick rates different displays produce.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "loadanimlayout.py"
FRAME_COUNT = 78
# Tick rates seen in practice: vblank-locked at 29.981 and 59.94 Hz, the
# maxfps=60 limiter's ~77 Hz, and 240 Hz with maxfps=0.
TICK_RATES = (29.981, 59.94, 76.9, 240.0)


class _Stub:
    def __init__(self, *args, **kwargs):
        pass


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def get_time(self):
        return self.now

    def schedule_interval(self, callback, timeout):
        return types.SimpleNamespace(cancel=lambda: None)


class _ImageBox:
    def __init__(self):
        self.added = []

    def add_widget(self, widget):
        self.added.append(widget)

    def remove_widget(self, widget):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def loadanim():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.app": _stub("kivy.app", App=_Stub),
        "kivy.clock": _stub("kivy.clock", Clock=_FakeClock()),
        "kivy.core": _stub("kivy.core"),
        "kivy.core.image": _stub("kivy.core.image", Image=_Stub),
        "kivy.lang": _stub("kivy.lang", Builder=types.SimpleNamespace(load_string=lambda kv: None)),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivy.properties": _stub(
            "kivy.properties", ListProperty=_Stub, BooleanProperty=_Stub,
            ObjectProperty=_Stub, NumericProperty=_Stub),
        "kivy.uix": _stub("kivy.uix"),
        "kivy.uix.effectwidget": _stub("kivy.uix.effectwidget", PixelateEffect=_Stub),
        "kivy.uix.image": _stub("kivy.uix.image", Image=_Stub),
        "kivy.uix.textinput": _stub("kivy.uix.textinput", TextInput=_Stub),
        "kivymd": _stub("kivymd"),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.boxlayout": _stub("kivymd.uix.boxlayout", MDBoxLayout=_Stub),
        "kivymd.uix.relativelayout": _stub("kivymd.uix.relativelayout", MDRelativeLayout=_Stub),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("KIVY_DATA_DIR", os.fspath(_PATH.parent))
            spec = importlib.util.spec_from_file_location("loadanimlayout_under_test", _PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


@pytest.fixture
def layout(loadanim):
    layout = loadanim.MWGGLoadingLayout.__new__(loadanim.MWGGLoadingLayout)
    layout.frames = [object() for _ in range(FRAME_COUNT)]
    layout.img_box = _ImageBox()
    layout.loading = True
    layout.current_image = None
    layout.current_frame = 0
    return layout


def _start(layout, speed):
    layout.set_speed(speed)
    layout.update_frame(0)


def _run(clock, layout, seconds, hz):
    """Tick at hz for seconds; return how many times the shown image changed."""
    before = len(layout.img_box.added)
    start = clock.now
    for tick in range(1, int(seconds * hz) + 1):
        clock.now = start + tick / hz
        layout.update_frame(1 / hz)
    return len(layout.img_box.added) - before


@pytest.mark.parametrize("hz", TICK_RATES)
def test_frame_rate_does_not_depend_on_tick_rate(loadanim, layout, hz):
    _start(layout, loadanim.DEFAULT_SPEED)
    changes = _run(loadanim.Clock, layout, 6.0, hz)
    assert abs(changes - 6.0 / loadanim.DEFAULT_SPEED) <= 1


@pytest.mark.parametrize("hz", TICK_RATES)
def test_frames_play_in_order_and_wrap(loadanim, layout, hz):
    _start(layout, loadanim.DEFAULT_SPEED)
    _run(loadanim.Clock, layout, 6.0, hz)
    shown = layout.img_box.added
    assert len(shown) > FRAME_COUNT
    assert shown == [layout.frames[i % FRAME_COUNT] for i in range(len(shown))]


@pytest.mark.parametrize("requested, bound", [(0.001, "MIN_SPEED"), (1.0, "MAX_SPEED")])
def test_speed_is_clamped(loadanim, layout, requested, bound):
    _start(layout, requested)
    changes = _run(loadanim.Clock, layout, 3.0, 240.0)
    assert abs(changes - 3.0 / getattr(loadanim, bound)) <= 1


def test_set_speed_keeps_the_shown_frame(loadanim, layout):
    _start(layout, loadanim.DEFAULT_SPEED)
    _run(loadanim.Clock, layout, 0.5, 240.0)
    shown = layout.current_frame
    assert shown > 0
    layout.set_speed(0.033)
    layout.update_frame(0)
    assert layout.current_frame == shown
    assert abs(_run(loadanim.Clock, layout, 0.99, 240.0) - 0.99 / 0.033) <= 1


def test_hidden_layout_stops_the_callback(layout):
    layout.loading = False
    assert layout.update_frame(0) is False
    assert layout.img_box.added == []
