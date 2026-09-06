"""Contract between beta's UIHint.get_classification and its GUI consumers.

The consumers (hint screen, console sorter, expansion list) import Kivy at
module level, so they are parsed with ast instead of imported. The label set
comes from the real classifier on the beta checkout conftest puts on sys.path,
so a rename on either side, or an item_colors key that the theme never
defines, fails here.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from BaseClasses import ItemClassification
from ui_dataclasses import UIHint

_GUI = Path(__file__).resolve().parent.parent / "mwgg_gui"
_CONSUMERS = {
    "hintscreen": _GUI / "hint" / "hintscreen.py",
    "console": _GUI / "console" / "console.py",
    "expansionlist": _GUI / "overrides" / "expansionlist.py",
}
_COLOR_CONSUMERS = ("hintscreen", "expansionlist")
_THEME = _GUI / "components" / "mw_theme.py"
# Labels the GUI assigns itself on top of the classifier's output.
_GUI_ONLY_LABELS = {"Found"}


def _classifier_labels() -> set[str]:
    all_bits = 0
    for member in ItemClassification:
        all_bits |= member
    return {UIHint.get_classification(flags) for flags in range(all_bits + 1)}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_classification(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "classification") or (
        isinstance(node, ast.Attribute) and node.attr == "classification"
    )


def _compared_labels(tree: ast.Module) -> set[str]:
    labels = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not _is_classification(node.left):
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                labels.add(comparator.value)
    return labels


def _item_color_keys_used(tree: ast.Module) -> set[str]:
    return {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "item_colors"
        and isinstance(node.slice, ast.Constant)
    }


def _item_color_definitions(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Keys of every ``item_colors = {...}`` literal and the markup_tags_theme
    attributes their values read."""
    keys, theme_attrs = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "item_colors" for t in node.targets):
            continue
        keys.update(k.value for k in node.value.keys if isinstance(k, ast.Constant))
        for sub in ast.walk(node.value):
            if (
                isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Attribute)
                and sub.value.attr == "markup_tags_theme"
            ):
                theme_attrs.add(sub.attr)
    return keys, theme_attrs


def _theme_fields() -> set[str]:
    for node in _parse(_THEME).body:
        if isinstance(node, ast.ClassDef) and node.name == "MarkupTagsTheme":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("MarkupTagsTheme not found in mw_theme.py")


@pytest.mark.parametrize("consumer", sorted(_CONSUMERS))
def test_consumer_handles_exactly_the_classifier_labels(consumer):
    compared = _compared_labels(_parse(_CONSUMERS[consumer]))
    expected = _classifier_labels()
    assert compared - expected - _GUI_ONLY_LABELS == set(), "labels the classifier never returns"
    assert expected - compared == set(), "classifier labels the consumer ignores"


@pytest.mark.parametrize("consumer", _COLOR_CONSUMERS)
def test_item_colors_keys_are_defined(consumer):
    tree = _parse(_CONSUMERS[consumer])
    defined, _ = _item_color_definitions(tree)
    assert defined, "no item_colors literal found"
    assert _item_color_keys_used(tree) - defined == set()


@pytest.mark.parametrize("consumer", _COLOR_CONSUMERS)
def test_item_colors_read_real_theme_attributes(consumer):
    _, theme_attrs = _item_color_definitions(_parse(_CONSUMERS[consumer]))
    assert theme_attrs, "item_colors literal reads no markup_tags_theme attributes"
    assert theme_attrs - _theme_fields() == set()
