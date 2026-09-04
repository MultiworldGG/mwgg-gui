"""Tests for mwgg_gui/hint/hint_visibility.py (classic table visibility helpers).

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


def test_hidden_bit_is_independent_of_the_flag_bits():
    shop_goal = 0b011
    assert hv.is_hidden(shop_goal) is False
    hidden = hv.with_hidden(shop_goal, True)
    assert hv.is_hidden(hidden) is True
    assert hidden & 0b111 == shop_goal
    assert hv.with_hidden(hidden, False) == shop_goal


def test_row_visible_switch_semantics():
    assert hv.row_visible(found=False, hidden=False, show_all=False) is True
    assert hv.row_visible(found=True, hidden=False, show_all=False) is False
    assert hv.row_visible(found=False, hidden=True, show_all=False) is False
    assert hv.row_visible(found=True, hidden=True, show_all=True) is True


def test_resolve_ui_hint_bucket_is_the_other_player():
    hint = {"receiving_player": 1, "finding_player": 2}
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: slot == 1) == 2
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: slot == 2) == 1
    assert hv.resolve_ui_hint_bucket(hint, lambda slot: False) is None
