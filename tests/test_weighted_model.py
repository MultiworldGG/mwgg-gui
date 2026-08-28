"""Tests for mwgg_gui/yaml_creator/weighted_model.py (loaded by file
path; see conftest.py). The weighted form's RecycleView renders from
these models, so they carry all option state: initial weight tables per
option type, YAML restore via apply_value, custom rows, and the
direct-value (set/dict/counter) summary models.
"""
from __future__ import annotations

import pytest

WORLD = {
    "item_names": ["Bow", "Sword", "Shield"],
    "location_names": ["Cave", "Castle"],
}


def _keys(model):
    return [e.key for e in model.entries]


# ----- toggle ---------------------------------------------------------------


def test_toggle_default_off(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 0}, {})
    assert m.value == {"false": 25, "true": 0, "random": 0}
    assert m.is_default()


def test_toggle_default_on_and_edit(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 1}, {})
    assert m.value == {"false": 0, "true": 25, "random": 0}
    m.set_weight("random", 10)
    assert not m.is_default()
    assert m.value["random"] == 10


def test_set_weight_clamps_and_ignores_unknown(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 0}, {})
    m.set_weight("true", 999)
    assert m.value["true"] == 50
    m.set_weight("nonsense", 25)
    assert "nonsense" not in m.value


# ----- choice ---------------------------------------------------------------


def test_choice_rows_and_default(weighted_model):
    m = weighted_model.model_for_option(
        {
            "name": "goal",
            "type": "choice",
            "choices": {"0": "kill_ganon", "1": "triforce_hunt"},
            "display_names": {"1": "Triforce Hunt"},
            "default": 1,
        },
        {},
    )
    assert _keys(m) == ["kill_ganon", "triforce_hunt", "random"]
    assert m.value == {"kill_ganon": 0, "triforce_hunt": 25, "random": 0}
    labels = {e.key: e.label for e in m.entries}
    assert labels["triforce_hunt"] == "Triforce Hunt"
    assert labels["kill_ganon"] == "kill_ganon"
    assert m.custom_hint is None


def test_text_choice_custom_rows(weighted_model):
    m = weighted_model.model_for_option(
        {
            "name": "c",
            "type": "text_choice",
            "choices": {"0": "vanilla"},
            "default": 0,
        },
        {},
    )
    assert m.custom_hint == "custom value"
    assert m.add_custom("  My Value  ") == "My Value"
    assert m.value["My Value"] == 25
    assert not m.is_default()
    # Duplicate returns the key without adding a second entry.
    before = len(m.entries)
    assert m.add_custom("My Value") == "My Value"
    assert len(m.entries) == before
    assert m.add_custom("   ") is None
    # Only removable entries can be removed.
    assert m.remove("vanilla") is False
    assert m.remove("My Value") is True
    assert "My Value" not in m.value


# ----- range / named range --------------------------------------------------


def test_range_interior_default(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "r", "type": "range", "range_start": 0, "range_end": 10, "default": 5},
        {},
    )
    assert _keys(m) == [
        "0", "5", "10", "random", "random-low", "random-middle", "random-high",
    ]
    assert m.value["5"] == 25
    assert next(e for e in m.entries if e.key == "5").removable


def test_range_endpoint_default_weights_endpoint(weighted_model):
    # An endpoint default must weight that endpoint's row; an all-zero
    # stack can't be rolled by the generator.
    m = weighted_model.model_for_option(
        {"name": "r", "type": "range", "range_start": 0, "range_end": 10, "default": 0},
        {},
    )
    assert m.value["0"] == 25
    assert sum(m.value.values()) == 25


def test_range_custom_coercion(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "r", "type": "range", "range_start": 1, "range_end": 8, "default": 4},
        {},
    )
    assert m.custom_hint == "integer value"
    assert m.add_custom("7") == "7"
    assert m.add_custom("9") is None
    assert m.add_custom("abc") is None


def test_named_range_special_default_outside_range(weighted_model):
    m = weighted_model.model_for_option(
        {
            "name": "nr",
            "type": "named_range",
            "range_start": 0,
            "range_end": 10,
            "default": -1,
            "special_range_names": {"unlimited": -1, "none": 0},
        },
        {},
    )
    assert m.value["unlimited"] == 25
    # "none" matches range_start's value but the default already claimed
    # its row; exactly one row carries the default weight.
    assert sum(1 for v in m.value.values() if v) == 1
    label = next(e.label for e in m.entries if e.key == "unlimited")
    assert label == "Unlimited (-1)"


# ----- free text ------------------------------------------------------------


def test_free_text_default_row(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "f", "type": "free_text", "default": "Link"}, {}
    )
    assert m.value == {"Link": 25}
    assert next(e for e in m.entries if e.key == "Link").removable
    empty = weighted_model.model_for_option(
        {"name": "f", "type": "free_text", "default": ""}, {}
    )
    assert empty.value == {}


# ----- apply_value (YAML restore) -------------------------------------------


def test_apply_value_updates_and_adds_custom(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 0}, {})
    assert m.apply_value({"true": 30, "extra": 5, "ghost": 0})
    assert m.value == {"false": 0, "true": 30, "random": 0, "extra": 5}
    extra = next(e for e in m.entries if e.key == "extra")
    assert extra.removable
    assert not any(e.key == "ghost" for e in m.entries)


def test_apply_value_rejects_garbage(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 0}, {})
    before = m.value
    assert not m.apply_value(["not", "a", "dict"])
    assert not m.apply_value({"true": "lots"})
    assert m.value == before


def test_apply_value_default_round_trip_is_default(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 1}, {})
    assert m.apply_value({"false": 0, "true": 25, "random": 0})
    assert m.is_default()


def test_most_likely_text(weighted_model):
    m = weighted_model.model_for_option({"name": "t", "type": "toggle", "default": 0}, {})
    assert m.most_likely_text() == "Locked to false"
    m.set_weight("true", 25)
    m.set_weight("random", 0)
    assert "50%" in m.most_likely_text()
    m.apply_value({"false": 0, "true": 0, "random": 0})
    assert "all weights zero" in m.most_likely_text()


# ----- direct-value models --------------------------------------------------


def test_item_set_direct(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "start_hints", "type": "item_set", "default": ["Sword"]}, WORLD
    )
    assert type(m).__name__ == "DirectOptionModel"
    assert m.value == ["Sword"]
    assert m.skip_when_default() and m.is_default()
    assert m.apply_value(["Bow", "Sword"])
    assert m.value == ["Bow", "Sword"]
    assert not m.is_default()
    assert "2 selected" in m.summary_text()
    assert not m.apply_value(42)


def test_option_set_filters_to_valid_keys(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "tricks", "type": "option_set", "valid_keys": ["a", "b"], "default": []},
        WORLD,
    )
    assert not m.skip_when_default()
    assert m.apply_value(["b", "z"])
    assert m.value == ["b"]


def test_mass_counter_direct(weighted_model):
    m = weighted_model.model_for_option(
        {
            "name": "start_inventory",
            "type": "option_counter",
            "verify_item_name": True,
            "default": {},
        },
        WORLD,
    )
    assert m.value == {}
    assert m.skip_when_default()
    assert m.apply_value({"Bow": 2, "Sword": 0})
    assert m.value == {"Bow": 2}
    assert "1 with non-zero count" in m.summary_text()


def test_valid_keys_counter_backfills_zeros(weighted_model):
    m = weighted_model.model_for_option(
        {
            "name": "counts",
            "type": "option_counter",
            "valid_keys": ["x", "y"],
            "default": {"x": 3},
        },
        WORLD,
    )
    assert m.value == {"x": 3, "y": 0}
    assert not m.skip_when_default()
    assert m.is_default()
    assert m.apply_value({"y": 1})
    assert m.value == {"x": 0, "y": 1}


def test_option_dict_not_editable(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "d", "type": "option_dict", "default": {"a": 1}}, WORLD
    )
    assert not m.editable
    assert m.value == {"a": 1}
    assert m.is_default()
    assert m.apply_value({"b": 2})
    assert m.value == {"b": 2}
    assert not m.apply_value("nope")


# ----- factory routing ------------------------------------------------------


def test_supports_weighting_false_forces_direct(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "t", "type": "toggle", "default": 0, "supports_weighting": False}, {}
    )
    assert type(m).__name__ == "DirectOptionModel"


def test_supports_weighting_field_missing_routes_by_type(weighted_model):
    direct = weighted_model.model_for_option(
        {"name": "s", "type": "location_set", "default": []}, WORLD
    )
    assert type(direct).__name__ == "DirectOptionModel"
    weighted = weighted_model.model_for_option(
        {"name": "c", "type": "choice", "choices": {"0": "a"}, "default": 0}, {}
    )
    assert "random" in weighted.value


def test_unknown_weightable_type_stays_editable(weighted_model):
    m = weighted_model.model_for_option(
        {"name": "m", "type": "mystery", "supports_weighting": True}, {}
    )
    assert m.custom_hint == "custom value"
    assert m.add_custom("thing") == "thing"
