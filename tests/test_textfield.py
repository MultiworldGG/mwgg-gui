"""Hint text position patch for MDTextField (overrides/textfield.py).

textfield.py imports Kivy and KivyMD at module level, so it is loaded by file
path with those imports stubbed; dp is the identity and Animation records the
targets it is started with.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "overrides" / "textfield.py"


class _Animation:
    def __init__(self, **targets):
        self.targets = targets

    def start(self, widget):
        widget.animated = self.targets


class _MDTextField:
    height = 56

    def set_pos_hint_text(self, y, x):
        raise AssertionError("upstream set_pos_hint_text still bound")


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def textfield():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.animation": _stub("kivy.animation", Animation=_Animation),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivymd": _stub("kivymd"),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.textfield": _stub("kivymd.uix.textfield", MDTextField=_MDTextField),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("mwgg_gui.overrides.textfield_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


def test_import_patches_the_upstream_class_once(textfield):
    assert _MDTextField.set_pos_hint_text is textfield.set_pos_hint_text
    assert textfield.patch_hint_text_position() is False


@pytest.mark.parametrize(("height", "expected_y"), [(56, 10), (40, 18), (72, 2)])
def test_hint_targets_shift_by_half_the_height_difference(textfield, height, expected_y):
    field = _MDTextField()
    field.height = height
    field.set_pos_hint_text(10, -3)
    assert field.animated["_hint_y"] == expected_y
    assert field.animated["_hint_x"] == -3
