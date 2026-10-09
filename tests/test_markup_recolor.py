"""Recoloring rendered console markup (console/markup_recolor.py).

The module is pure Python over NetUtils.bbcode_gradient, so it is loaded by
file path; the mwgg_gui package __init__ (and Kivy) never import.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

NetUtils = pytest.importorskip(
    "NetUtils", reason="beta core not importable - set MWGG_BETA_SRC to the MultiworldGG/src checkout"
)

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "console" / "markup_recolor.py"


@pytest.fixture(scope="module")
def recolor_markup():
    spec = importlib.util.spec_from_file_location("markup_recolor_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.recolor_markup


# Light -> dark default_color and location_color, and two item colors.
REMAP = {"080808": "fafafa", "006f10": "00c51b", "a46a00": "ffbe00", "419f44": "6EC471"}


def test_single_color_tags_follow_the_remap(recolor_markup):
    markup = "[color=080808]Hello [/color][color=006F10]Sword Cave[/color][color=#ff0000]x[/color]"

    assert recolor_markup(markup, REMAP) == (
        "[color=fafafa]Hello [/color][color=00c51b]Sword Cave[/color][color=#ff0000]x[/color]"
    )


def test_gradient_is_regenerated_from_remapped_end_colors(recolor_markup):
    old = NetUtils.bbcode_gradient("419F44", "a46a00", "Master Sword &bl;1&br;")
    markup = f"[color=080808]Got [/color][ref=0|Item Class: progression, useful]{old}[/ref]"

    new = NetUtils.bbcode_gradient("6EC471", "ffbe00", "Master Sword &bl;1&br;")
    assert recolor_markup(markup, REMAP) == (
        f"[color=fafafa]Got [/color][ref=0|Item Class: progression, useful]{new}[/ref]"
    )


def test_runs_stop_at_line_breaks(recolor_markup):
    gradient = NetUtils.bbcode_gradient("419f44", "a46a00", "Bow")
    markup = f"{gradient}\n[color=006f10]A[/color][color=080808]:[/color]"

    assert recolor_markup(markup, REMAP) == (
        NetUtils.bbcode_gradient("6EC471", "ffbe00", "Bow")
        + "\n[color=00c51b]A[/color][color=fafafa]:[/color]"
    )


def test_adjacent_single_glyph_nodes_that_are_not_a_gradient(recolor_markup):
    markup = "[color=006f10]A[/color][color=080808]-[/color][color=a46a00]B[/color]"

    assert recolor_markup(markup, REMAP) == (
        "[color=00c51b]A[/color][color=fafafa]-[/color][color=ffbe00]B[/color]"
    )


def test_swapped_colors_do_not_chain(recolor_markup):
    markup = "[color=111111]a[/color] [color=222222]bb[/color]"

    assert recolor_markup(markup, {"111111": "222222", "222222": "111111"}) == (
        "[color=222222]a[/color] [color=111111]bb[/color]"
    )


def test_empty_remap_returns_markup_unchanged(recolor_markup):
    markup = "[color=080808]unchanged[/color]"

    assert recolor_markup(markup, {}) is markup
