"""Per-tick uniform writes of SafeEffectWidget (components/safe_effect_widget.py).

The module is loaded by file path with kivy.uix.effectwidget stubbed, so the
override runs against plain dicts instead of GL render contexts.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "safe_effect_widget.py"


class _EffectWidget:
    pass


@pytest.fixture(scope="module")
def safe_effect_widget():
    stubs = {
        "kivy": types.ModuleType("kivy"),
        "kivy.uix": types.ModuleType("kivy.uix"),
        "kivy.uix.effectwidget": types.ModuleType("kivy.uix.effectwidget"),
    }
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
