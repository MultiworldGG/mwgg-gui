"""Tests for mwgg_gui/hint/hint_refresh.py (hint screen rebuild change detection).

hint_refresh.py is import-light (no kivy), so it is loaded by file path here,
bypassing mwgg_gui/hint/__init__ (which imports the full Kivy GUI).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "hint" / "hint_refresh.py"
)


def _load_hint_refresh():
    spec = importlib.util.spec_from_file_location("hint_refresh_under_test", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hr = _load_hint_refresh()


def _hint(location: int, finding: int = 2, receiving: int = 1, status: int = 1) -> dict:
    return {"receiving_player": receiving, "finding_player": finding, "location": location,
            "item": 100 + location, "found": False, "entrance": "", "item_flags": 1, "status": status}


HINTS = [_hint(10), _hint(11, finding=3)]
MWGG = {"2_10": 0b001}
PROFILES = {1: {"slot_id": 1, "slot_name": "me", "avatar": "", "pronouns": "", "bk_mode": False, "deafened": False}}


class _LogicColumn:
    """Stand-in for the tracker's registered in_logic column."""
    key = "in_logic"

    def __init__(self):
        self.in_logic: set[int] = set()

    def build_value(self, hint: dict, row: dict) -> None:
        row[self.key] = {"state": "in_logic" if hint["location"] in self.in_logic else "not_found"}


def test_same_inputs_match_regardless_of_hint_order():
    forward = hr.render_signature(HINTS, MWGG, PROFILES, True)
    reversed_ = hr.render_signature(list(reversed(HINTS)), dict(MWGG), dict(PROFILES), True)
    assert forward == reversed_


def test_hint_status_and_mwgg_flags_and_names_change_the_signature():
    base = hr.render_signature(HINTS, MWGG, PROFILES, True)
    assert hr.render_signature([_hint(10, status=4), HINTS[1]], MWGG, PROFILES, True) != base
    assert hr.render_signature(HINTS, {"2_10": 0b011}, PROFILES, True) != base
    assert hr.render_signature(HINTS, MWGG, PROFILES, False) != base


def test_profile_change_rebuilds_the_sidebar():
    base = hr.render_signature(HINTS, MWGG, PROFILES, True)
    changed = {1: {**PROFILES[1], "avatar": "ap:avatar.png"}}
    assert hr.render_signature(HINTS, MWGG, changed, True) != base


def test_registered_column_state_is_part_of_the_signature():
    column = _LogicColumn()
    base = hr.render_signature(HINTS, MWGG, PROFILES, True, [column])
    assert hr.render_signature(HINTS, MWGG, PROFILES, True, [column]) == base
    column.in_logic.add(10)
    assert hr.render_signature(HINTS, MWGG, PROFILES, True, [column]) != base
