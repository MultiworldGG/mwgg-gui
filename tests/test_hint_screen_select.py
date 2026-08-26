"""Tests for mwgg_gui/hint/select.py — hint-screen style resolution.

select.py is deliberately import-light, so it is loaded by file path here
(bypassing mwgg_gui/__init__, which imports the full Kivy GUI). The new
screen is represented by the ``None`` sentinel precisely so these tests
never import mwgg_gui.hint.hintscreen (whose module-level kivy.core.window
import would open an SDL window under pytest).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SELECT_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "hint" / "select.py"
)


def _load_select():
    spec = importlib.util.spec_from_file_location(
        "hint_select_under_test", _SELECT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_kvui(with_classic: bool):
    module = types.ModuleType("kvui")
    if with_classic:
        class ClassicHintScreen:  # stand-in for the real kvui class
            pass
        module.ClassicHintScreen = ClassicHintScreen
    return module


def test_classic_with_class_present(monkeypatch):
    fake = _fake_kvui(with_classic=True)
    monkeypatch.setitem(sys.modules, "kvui", fake)
    select = _load_select()
    assert select.resolve_hint_screen_class("classic") is fake.ClassicHintScreen


def test_classic_normalizes_case_and_whitespace(monkeypatch):
    fake = _fake_kvui(with_classic=True)
    monkeypatch.setitem(sys.modules, "kvui", fake)
    select = _load_select()
    assert select.resolve_hint_screen_class("  Classic\n") is fake.ClassicHintScreen


def test_classic_without_class_falls_back_to_new(monkeypatch):
    monkeypatch.setitem(sys.modules, "kvui", _fake_kvui(with_classic=False))
    select = _load_select()
    assert select.resolve_hint_screen_class("classic") is None


def test_classic_with_kvui_import_failure_falls_back_to_new(monkeypatch):
    # A None sys.modules entry makes `import kvui` raise ImportError.
    monkeypatch.setitem(sys.modules, "kvui", None)
    select = _load_select()
    assert select.resolve_hint_screen_class("classic") is None


def test_non_classic_values_return_new_even_when_classic_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "kvui", _fake_kvui(with_classic=True))
    select = _load_select()
    for style in ("new", " New ", "", "weird", None):
        assert select.resolve_hint_screen_class(style) is None
