"""Tests for mwgg_gui/components/columns.py — the column sort/filter registry.

columns.py is deliberately import-light (no kivy), so it is loaded by file
path here, bypassing mwgg_gui/__init__ (which imports the full Kivy GUI).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_COLUMNS_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "columns.py"
)


def _load_columns():
    spec = importlib.util.spec_from_file_location("columns_under_test", _COLUMNS_PATH)
    module = importlib.util.module_from_spec(spec)
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
