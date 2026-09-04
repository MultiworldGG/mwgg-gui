"""Emily's Column sort/filter registry mixins.

Moving ColumnSorter / ColumnFilter and their mixins out of kvui.py (might change 
my mind on this). World code such as the
Universal Tracker registers sorters and filters against ``kvui.HintLog``, an
alias for this package's ConsoleSliverAppbar. These classes mirror the kvui
interface so that registration works against our widgets; consumers must stay
duck-typed because registrants hand over kvui's instances, not ours.
"""
from __future__ import annotations

import dataclasses
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

    def build_menu_items(self, data: list[typing.Any]) -> list[dict]:
        """Toggle entries for a filter menu: ``{"text", "active", "on_toggle"}``,
        where on_toggle(active) moves the name out of / into the denylist."""
        menu_items = []
        for name in self.get_basic_menu_names(data):
            def toggle(active: bool, name=name) -> None:
                if active:
                    self.filter_denylist.discard(name)
                else:
                    self.filter_denylist.add(name)
            menu_items.append({
                "text": name,
                "active": name not in self.filter_denylist,
                "on_toggle": toggle,
            })
        return menu_items


class ColumnFilterMulti(ColumnFilter):
    """Filter for a column whose rows carry several values at once (the hint
    flags column); str_conv_func returns an iterable of names."""

    def _values(self, value: typing.Any) -> set[str] | None:
        if self.str_conv_func:
            value = self.str_conv_func(value)
        if value is None:
            return None
        if isinstance(value, str):
            return {value}
        return set(value)

    def filter_data(self, value: typing.Any) -> bool:
        values = self._values(value)
        if values is None:
            return not self.filter_allowlist
        if self.filter_allowlist and not values & self.filter_allowlist:
            return False
        return not values & self.filter_denylist

    def get_basic_menu_names(self, data: list[typing.Any]) -> list[str]:
        shown_values = self.option_list | self.filter_denylist
        for value in data:
            values = self._values(value)
            if values:
                shown_values.update(values)
        return sorted(shown_values)


class ColumnFilterItemClassification(ColumnFilter):
    """Item-column filter with required / hidden classification bits on top of
    the plain name filter (upstream kvui)."""
    req_flags: int = 0
    hide_flags: int = 0
    hide_filler: bool = False
    iclass_conv_func: typing.Callable[[typing.Any], int | None] | None

    _flags = (
        ("Progression", 0b001),
        ("Useful", 0b010),
        ("Trap", 0b100),
    )

    def __init__(self, key: str, str_conv_func: typing.Callable[[typing.Any], str | None] | None = None,
                 iclass_conv_func: typing.Callable[[typing.Any], int | None] | None = None):
        super().__init__(key, str_conv_func)
        self.iclass_conv_func = iclass_conv_func

    def build_menu_items(self, data: list[typing.Any]) -> list[dict]:
        menu_items = []
        for name, bit in self._flags:
            def toggle_req(active: bool, bit=bit) -> None:
                self.req_flags = self.req_flags | bit if active else self.req_flags & ~bit
            menu_items.append({
                "text": f"Req. {name}",
                "active": bool(self.req_flags & bit),
                "on_toggle": toggle_req,
            })
        for name, bit in self._flags:
            def toggle_hide(active: bool, bit=bit) -> None:
                self.hide_flags = self.hide_flags | bit if active else self.hide_flags & ~bit
            menu_items.append({
                "text": f"Hide {name}",
                "active": bool(self.hide_flags & bit),
                "on_toggle": toggle_hide,
            })
        menu_items.append({
            "text": "Hide Filler",
            "active": self.hide_filler,
            "on_toggle": lambda active: setattr(self, "hide_filler", active),
        })
        menu_items.extend(super().build_menu_items(data))
        return menu_items

    def filter_classification(self, value: int) -> bool:
        if self.hide_filler and not value:
            return False
        if value & self.req_flags != self.req_flags:
            return False
        if value & self.hide_flags:
            return False
        return True

    def filter_data(self, value: typing.Any) -> bool:
        if self.iclass_conv_func:
            classification = self.iclass_conv_func(value)
            if not self.filter_classification(classification or 0):
                return False
        return super().filter_data(value)


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


@dataclasses.dataclass
class ExtraColumn:
    """A hint-table column contributed by world code (e.g. the tracker's
    in-logic status), registered against ``kvui.HintLog`` rather than baked
    into the base table."""
    key: str
    header_text: str
    # (raw hint dict, row dict being built) -> None; sets row[key].
    build_value: typing.Callable[[dict, dict], None]
    sorter: ColumnSorter
    filter: ColumnFilter | None = None


_extra_columns: dict[str, ExtraColumn] = {}


def register_extra_column(column: ExtraColumn) -> None:
    """Register (or replace) an extra hint-table column, keyed by ``column.key``
    so relaunching a client doesn't accumulate duplicates."""
    _extra_columns[column.key] = column


def get_extra_columns() -> list[ExtraColumn]:
    return list(_extra_columns.values())


def clear_extra_columns() -> None:
    """Test-only reset of the registry."""
    _extra_columns.clear()
