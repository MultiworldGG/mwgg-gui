"""Tests for mwgg_gui/hint/hint_visibility.py (classic table hidden flag helpers).

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


def test_hidden_payload_covers_every_key_and_keeps_flags():
    stored = {"2_10": 0b100, "2_11": 0b1001, "3_5": None}
    keys = ["2_10", "2_11", "3_5", "4_1"]
    assert hv.hidden_payload(keys, stored, True) == {"2_10": 0b1100, "2_11": 0b1001, "3_5": 0b1000, "4_1": 0b1000}
    assert hv.hidden_payload(keys, stored, False) == {"2_10": 0b100, "2_11": 0b001, "3_5": 0, "4_1": 0}
