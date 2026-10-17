"""SafeEffectWidget's uniform writes and effect FBO redraws (components/safe_effect_widget.py).

The module is loaded by file path with kivy.uix.effectwidget and kivy.graphics
stubbed, so the overrides run against plain containers instead of GL render
contexts.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "safe_effect_widget.py"


class _Group(list):
    active = None

    def __enter__(self):
        _Group.active = self

    def __exit__(self, *exc):
        _Group.active = None


class _Callback:
    def __init__(self, callback):
        self.callback = callback
        _Group.active.append(self)


class _Canvas(list):
    def indexof(self, instruction):
        return self.index(instruction)


class _Fbo:
    def __init__(self):
        self.after = _Group()
        self.updates = 0

    def ask_update(self):
        self.updates += 1


class _EffectWidget:
    """Mirrors Kivy: the content FBO leads the canvas, effect FBOs are appended."""

    def __init__(self, **kwargs):
        self.fbo = _Fbo()
        self.canvas = _Canvas(["before", self.fbo, "color", "output_rect", "after"])
        self.fbo_list = []
        self.effects = []
        self.size = (300, 40)

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def refresh_fbo_setup(self, *args):
        while len(self.fbo_list) < len(self.effects):
            fbo = _Fbo()
            self.canvas.append(fbo)
            self.fbo_list.append(fbo)


@pytest.fixture(scope="module")
def safe_effect_widget():
    stubs = {
        "kivy": types.ModuleType("kivy"),
        "kivy.graphics": types.ModuleType("kivy.graphics"),
        "kivy.uix": types.ModuleType("kivy.uix"),
        "kivy.uix.effectwidget": types.ModuleType("kivy.uix.effectwidget"),
    }
    stubs["kivy.graphics"].Callback = _Callback
    stubs["kivy.uix.effectwidget"].EffectWidget = _EffectWidget
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("safe_effect_widget_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


def _widget(module, size, fbo_count):
    widget = module.SafeEffectWidget()
    widget.size = size
    widget.canvas = {}
    widget.fbo_list = [{} for _ in range(fbo_count)]
    return widget


def test_update_glsl_writes_resolution_and_never_time(safe_effect_widget):
    widget = _widget(safe_effect_widget, (300, 40), fbo_count=2)
    widget._update_glsl(0.016)
    assert widget.canvas == {"resolution": [300.0, 40.0]}
    assert widget.fbo_list == [{"resolution": [300.0, 40.0]}] * 2


def test_update_glsl_follows_size_changes(safe_effect_widget):
    widget = _widget(safe_effect_widget, (300, 40), fbo_count=1)
    widget._update_glsl(0.016)
    widget.size = (640, 48)
    widget._update_glsl(0.016)
    assert widget.canvas == {"resolution": [640.0, 48.0]}
    assert widget.fbo_list == [{"resolution": [640.0, 48.0]}]


def test_content_redraw_flags_every_effect_fbo(safe_effect_widget):
    widget = safe_effect_widget.SafeEffectWidget()
    widget.effects = ["vertical", "horizontal"]
    widget.refresh_fbo_setup()
    (callback,) = widget.fbo.after
    callback.callback(callback)
    assert [fbo.updates for fbo in widget.fbo_list] == [1, 1]


def test_effect_fbos_draw_before_the_output_rectangle(safe_effect_widget):
    widget = safe_effect_widget.SafeEffectWidget()
    widget.effects = ["vertical", "horizontal"]
    widget.refresh_fbo_setup()
    first, second = widget.fbo_list
    assert widget.canvas == ["before", widget.fbo, first, second, "color", "output_rect", "after"]

    widget.effects = ["vertical", "horizontal", "pixelate"]
    widget.refresh_fbo_setup()
    third = widget.fbo_list[2]
    assert widget.canvas == ["before", widget.fbo, first, second, third, "color", "output_rect", "after"]


def test_zero_size_skips_fbo_setup(safe_effect_widget):
    widget = safe_effect_widget.SafeEffectWidget()
    widget.effects = ["vertical"]
    widget.size = (0, 40)
    widget.refresh_fbo_setup()
    assert widget.fbo_list == []
    assert widget.canvas == ["before", widget.fbo, "color", "output_rect", "after"]
