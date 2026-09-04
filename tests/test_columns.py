"""Tests for mwgg_gui/components/columns.py, the column sort/filter registry.

columns.py is deliberately import-light (no kivy), so it is loaded by file
path here, bypassing mwgg_gui/__init__ (which imports the full Kivy GUI).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_COLUMNS_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "columns.py"
)


def _load_columns():
    spec = importlib.util.spec_from_file_location("columns_under_test", _COLUMNS_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations via sys.modules[cls.__module__]; register
    # before exec or ExtraColumn's @dataclass decorator crashes on AttributeError.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


columns = _load_columns()


def _logic_sorter(reverse=False):
    # Mirrors the tracker's sort weights: in-logic first, found last.
    weights = {"in_logic": 0, "not_found": 1, "found": 2}
    return columns.ColumnSorter("in_logic", lambda row: weights[row["state"]], reverse)


def test_sorter_sorts_by_func_and_reverse():
    rows = [{"state": "found"}, {"state": "in_logic"}, {"state": "not_found"}]
    sorter = _logic_sorter()
    sorter.sort(rows)
    assert [r["state"] for r in rows] == ["in_logic", "not_found", "found"]
    sorter.reverse = True
    sorter.sort(rows)
    assert [r["state"] for r in rows] == ["found", "not_found", "in_logic"]


def test_sort_mixin_registration_and_sort_by_key():
    class Host(columns.ColumnSortMixin):
        pass

    host = Host()
    assert host.column_sorters == []
    assert host.sort_by_key("in_logic") is False

    sorter = _logic_sorter()
    host.column_sorters.append(sorter)
    assert host.get_sorter("in_logic") is sorter
    assert host.get_sorter("other") is None

    # Key already primary (last in list): sort_by_key flips its direction.
    assert host.sort_by_key("in_logic") is True
    assert sorter.reverse is True

    other = columns.ColumnSorter("other", lambda row: 0)
    host.column_sorters.append(other)
    # Non-primary key moves to the end (becomes primary) without flipping.
    assert host.sort_by_key("in_logic") is True
    assert host.column_sorters[-1] is sorter
    assert sorter.reverse is True


def test_filter_deny_and_allow_lists():
    filt = columns.ColumnFilter("in_logic", lambda row: row["state"])
    assert filt.filter_data({"state": "found"}) is True

    filt.filter_denylist.add("found")
    assert filt.filter_data({"state": "found"}) is False
    assert filt.filter_data({"state": "in_logic"}) is True

    filt.filter_allowlist.add("in_logic")
    assert filt.filter_data({"state": "in_logic"}) is True
    assert filt.filter_data({"state": "not_found"}) is False


def test_filter_without_str_conv_passes_non_strings():
    filt = columns.ColumnFilter("anything")
    assert filt.filter_data({"state": "found"}) is True
    filt.filter_denylist.add("found")
    assert filt.filter_data("found") is False
    assert filt.filter_data("in_logic") is True


def test_get_basic_menu_names_merges_options_denials_and_data():
    filt = columns.ColumnFilter("in_logic", lambda row: row.get("state"))
    filt.option_list = {"Found", "In Logic", "Not Found"}
    filt.filter_denylist.add("Found")
    names = filt.get_basic_menu_names([{"state": "Extra"}, {"state": None}])
    assert names == ["Extra", "Found", "In Logic", "Not Found"]


def test_filter_mixin_filters_rows():
    class Host(columns.ColumnFilterMixin):
        pass

    host = Host()
    assert host.column_filters == []

    filt = columns.ColumnFilter("in_logic", lambda row: row["state"])
    host.column_filters.append(filt)
    assert host.get_filter("in_logic") is filt

    rows = [{"state": "found"}, {"state": "in_logic"}]
    assert host.filter_columns(rows) == rows
    filt.filter_denylist.add("found")
    assert host.filter_columns(rows) == [{"state": "in_logic"}]


def test_mixins_cooperate_with_kwargs_chain():
    class Base:
        def __init__(self, **kwargs):
            self.base_saw = kwargs.pop("marker", None)
            super().__init__(**kwargs)

    class Host(Base, columns.ColumnSortMixin, columns.ColumnFilterMixin):
        pass

    host = Host(marker=1)
    assert host.base_saw == 1
    assert host.column_sorters == []
    assert host.column_filters == []


def test_build_menu_items_toggles_denylist():
    filt = columns.ColumnFilter("status", lambda row: row["status"])
    filt.filter_denylist.add("Found")
    items = filt.build_menu_items([{"status": "Priority"}])
    assert [(i["text"], i["active"]) for i in items] == [("Found", False), ("Priority", True)]

    items[0]["on_toggle"](True)
    assert "Found" not in filt.filter_denylist
    items[1]["on_toggle"](False)
    assert filt.filter_denylist == {"Priority"}


def test_multi_filter_matches_any_value():
    filt = columns.ColumnFilterMulti("flags", lambda row: row.get("flags"))
    rows = [{"flags": ["Goal", "Shop"]}, {"flags": ["BK Mode"]}, {"flags": []}]
    assert all(filt.filter_data(row) for row in rows)
    assert filt.filter_data({}) is True

    filt.filter_denylist.add("Shop")
    assert [filt.filter_data(row) for row in rows] == [False, True, True]

    filt.filter_denylist.clear()
    filt.filter_allowlist.add("Goal")
    assert [filt.filter_data(row) for row in rows] == [True, False, False]
    # No value at all only passes while nothing is allowlisted.
    assert filt.filter_data({}) is False


def test_multi_filter_menu_names_merge_options_and_row_values():
    filt = columns.ColumnFilterMulti("flags", lambda row: row["flags"])
    filt.option_list = {"None"}
    filt.filter_denylist.add("Shop")
    names = filt.get_basic_menu_names([{"flags": ["Goal", "BK Mode"]}, {"flags": []}])
    assert names == ["BK Mode", "Goal", "None", "Shop"]


def test_item_classification_filter_flags_and_names():
    filt = columns.ColumnFilterItemClassification(
        "item", lambda row: row["name"], lambda row: row["flags"])
    rows = [{"name": "Sword", "flags": 0b001}, {"name": "Bomb", "flags": 0b100},
            {"name": "Rupee", "flags": 0}]
    assert all(filt.filter_data(row) for row in rows)

    items = filt.build_menu_items(rows)
    assert [i["text"] for i in items] == [
        "Req. Progression", "Req. Useful", "Req. Trap",
        "Hide Progression", "Hide Useful", "Hide Trap", "Hide Filler",
        "Bomb", "Rupee", "Sword"]

    items[0]["on_toggle"](True)  # Req. Progression
    assert filt.req_flags == 0b001
    assert [filt.filter_data(row) for row in rows] == [True, False, False]
    items[0]["on_toggle"](False)

    items[5]["on_toggle"](True)  # Hide Trap
    assert [filt.filter_data(row) for row in rows] == [True, False, True]
    items[6]["on_toggle"](True)  # Hide Filler
    assert [filt.filter_data(row) for row in rows] == [True, False, False]
    items[6]["on_toggle"](False)
    items[5]["on_toggle"](False)

    items[9]["on_toggle"](False)  # deny the name "Sword"
    assert [filt.filter_data(row) for row in rows] == [False, True, True]


def test_extra_column_registry_replaces_by_key():
    columns.clear_extra_columns()
    try:
        first = columns.ExtraColumn("in_logic", "In Logic", lambda hint, row: None, _logic_sorter())
        columns.register_extra_column(first)
        assert columns.get_extra_columns() == [first]

        second = columns.ExtraColumn("in_logic", "In Logic", lambda hint, row: None, _logic_sorter())
        columns.register_extra_column(second)
        assert columns.get_extra_columns() == [second]

        other = columns.ExtraColumn("other", "Other", lambda hint, row: None, _logic_sorter())
        columns.register_extra_column(other)
        assert columns.get_extra_columns() == [second, other]
    finally:
        columns.clear_extra_columns()


def test_extra_column_build_value_populates_row():
    calls = []

    def build_value(hint, row):
        calls.append(hint)
        row["in_logic"] = {"text": "In Logic", "state": "in_logic"}

    column = columns.ExtraColumn("in_logic", "In Logic", build_value, _logic_sorter())
    hint = {"location": 5}
    row = {}
    column.build_value(hint, row)
    assert calls == [hint]
    assert row == {"in_logic": {"text": "In Logic", "state": "in_logic"}}
