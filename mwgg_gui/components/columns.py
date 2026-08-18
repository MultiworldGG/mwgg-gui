"""Column sort/filter registry shared with the monorepo's kvui module.

The MultiworldGG monorepo ships upstream Archipelago's column machinery in
kvui.py (ColumnSorter / ColumnFilter and their mixins). World code such as the
Universal Tracker registers sorters and filters against ``kvui.HintLog`` — an
alias for this package's ConsoleSliverAppbar. These classes mirror the kvui
interface so that registration works against our widgets; consumers must stay
duck-typed because registrants hand over kvui's instances, not ours.

Import-light on purpose: no kivy imports, so unit tests can load it by path.
The dropdown UI half of upstream's ColumnFilter is intentionally absent — the
hint screen surfaces filter options through its native chip row instead.
"""
from __future__ import annotations

import typing


class ColumnSorter:
    key: str
    sort_func: typing.Callable[[typing.Any], typing.Any]
    reverse: bool

    def __init__(self, key: str, sort_func: typing.Callable[[typing.Any], typing.Any], reverse: bool = False):
        self.key = key
        self.sort_func = sort_func
        self.reverse = reverse

    def sort(self, data: list[typing.Any]):
        data.sort(key=self.sort_func, reverse=self.reverse)


class ColumnSortMixin:
    column_sorters: list[ColumnSorter]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.column_sorters = []

    def get_sorter(self, key: str) -> ColumnSorter | None:
        for sorter in self.column_sorters:
            if sorter.key == key:
                return sorter
        return None

    def sort_by_key(self, key: str) -> bool:
        found_sorter = self.get_sorter(key)
        if found_sorter:
            idx = self.column_sorters.index(found_sorter)
            if idx == len(self.column_sorters) - 1:  # reverse the order if already primarily sorted by this key
                found_sorter.reverse = not found_sorter.reverse
            else:
                self.column_sorters.append(self.column_sorters.pop(idx))  # move this sorter to the end
            return True
        return False

    def sort_columns(self, data: list[typing.Any]):
        for sorter in self.column_sorters:
            sorter.sort(data)


class ColumnFilter:
    key: str  # Which column key this filter belongs to
    str_conv_func: typing.Callable[[typing.Any], str | None] | None  # How to turn the data into simple strings
    filter_denylist: set[str]  # Strings to disallow / hide
    filter_allowlist: set[str]  # Strings to allow. If non-empty, disallows all not in this list.
    option_list: set[str]  # Strings to show, whether they are currently in the data or not

    def __init__(self, key: str, str_conv_func: typing.Callable[[typing.Any], str | None] | None = None):
        self.key = key
        self.str_conv_func = str_conv_func
        self.filter_denylist = set()
        self.filter_allowlist = set()
        self.option_list = set()

    def filter_str(self, value: str) -> bool:
        if self.filter_allowlist and value not in self.filter_allowlist:
            return False
        if value in self.filter_denylist:
            return False
        return True

    def filter_data(self, value: typing.Any) -> bool:
        if self.str_conv_func:
            value = self.str_conv_func(value)
        if isinstance(value, str):
            return self.filter_str(value)
        return not self.filter_allowlist

    def get_basic_menu_names(self, data: list[typing.Any]) -> list[str]:
        """All option labels to offer: declared options, currently denied ones,
        and whatever the data itself yields. Named after the upstream kvui
        method so registered kvui instances answer the same call."""
        shown_values = (self.option_list | self.filter_denylist)
        for value in data:
            if self.str_conv_func:
                converted = self.str_conv_func(value)
                if converted is None:
                    continue
                shown_values.add(converted)
            elif isinstance(value, str):
                shown_values.add(value)
        return sorted(shown_values)


class ColumnFilterMixin:
    column_filters: list[ColumnFilter]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.column_filters = []

    def get_filter(self, key: str) -> ColumnFilter | None:
        for filt in self.column_filters:
            if filt.key == key:
                return filt
        return None

    def filter_columns(self, data: list[typing.Any]) -> list[typing.Any]:
        return [datum for datum in data if all(filt.filter_data(datum) for filt in self.column_filters)]
