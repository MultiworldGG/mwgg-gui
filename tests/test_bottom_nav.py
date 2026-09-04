"""Ordering rules for the bottom-bar navigation (components/bottom_nav.py).

Loaded by file path so the test never imports mwgg_gui (and thus Kivy).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "bottom_nav.py"


@pytest.fixture(scope="module")
def bottom_nav():
    spec = importlib.util.spec_from_file_location("bottom_nav", _PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the module through sys.modules to evaluate the
    # postponed annotations.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _names(entries) -> list[str]:
    return [entry.name for entry in entries]


def test_console_and_hint_are_the_defaults(bottom_nav):
    entries = bottom_nav.nav_entries(["console"], [], admin_enabled=False)
    assert _names(entries) == ["console", "hint"]


def test_tracker_and_map_follow_their_screens_in_fixed_order(bottom_nav):
    tabs = [bottom_nav.ClientTab("map"), bottom_nav.ClientTab("tracker")]
    entries = bottom_nav.nav_entries(
        ["console", "hint", "map", "tracker"], tabs, admin_enabled=False)
    assert _names(entries) == ["console", "hint", "tracker", "map"]


def test_admin_follows_the_setting_not_the_screen(bottom_nav):
    assert "admin" not in _names(
        bottom_nav.nav_entries(["console", "admin"], [], admin_enabled=False))
    assert _names(bottom_nav.nav_entries(["console"], [], admin_enabled=True)) == \
        ["console", "hint", "admin"]


def test_client_tabs_append_after_builtins(bottom_nav):
    tabs = [
        bottom_nav.ClientTab("2048 Game", content=object(), icon="gamepad-variant-outline"),
        bottom_nav.ClientTab("tracker"),
    ]
    entries = bottom_nav.nav_entries(
        ["console", "tracker", "2048 Game"], tabs, admin_enabled=True)
    assert _names(entries) == ["console", "hint", "tracker", "admin", "2048 Game"]
    assert entries[-1].label == "2048 Game"
    assert entries[-1].icon == "gamepad-variant-outline"


def test_client_tab_handle_keeps_the_legacy_text_alias(bottom_nav):
    tab = bottom_nav.ClientTab("2048 Game")
    assert tab.text == "2048 Game"
    assert tab.icon == "puzzle-outline"
    assert tab.content is None
