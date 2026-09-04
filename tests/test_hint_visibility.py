"""Tests for mwgg_gui/hint/hint_visibility.py, the classic table's show-all logic.

hint_visibility.py is import-light (no kivy), so it is loaded by file path
here, bypassing mwgg_gui/hint/__init__ (which imports the full Kivy GUI).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "hint" / "hint_visibility.py"
)


def _load_hint_visibility():
    spec = importlib.util.spec_from_file_location("hint_visibility_under_test", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hv = _load_hint_visibility()


def test_resolve_ui_hint_bucket_prefers_receiving_side():
    hint = {"receiving_player": 1, "finding_player": 2}
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: slot == 1) == 2


def test_resolve_ui_hint_bucket_falls_back_to_finding_side():
    hint = {"receiving_player": 1, "finding_player": 2}
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: slot == 2) == 1


def test_resolve_ui_hint_bucket_none_when_neither_side_concerns_self():
    hint = {"receiving_player": 1, "finding_player": 2}
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: False) is None


def test_row_is_visible_matches_new_screen_semantics():
    assert hv.row_is_visible(hidden=False, show_all=False) is True
    assert hv.row_is_visible(hidden=True, show_all=False) is False
    assert hv.row_is_visible(hidden=True, show_all=True) is True
    assert hv.row_is_visible(hidden=False, show_all=True) is True
