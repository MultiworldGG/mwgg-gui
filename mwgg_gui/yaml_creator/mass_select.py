"""
Mass-selection row widgets for worlds with 500+ items or locations.

Backed by MDRecycleView so scrolling stays smooth even with multi-thousand
item lists. The rest of the codebase treats RecycleView as legacy, but
nothing else holds up at ALTTP-class scales — see plan for rationale.

`MassMultiSelectRow`  — for ItemSet / LocationSet.
`MassCounterRow`      — for OptionCounter with `verify_item_name` or
                        `verify_location_name`.
`ChecklistSelectRow`  — for OptionSet whose keys don't fit chips (see
                        `_chips_fit` in option_widgets.py); search +
                        checkbox list + summary, no chip wrap.

Layout:
    [search MDTextField                                          ]
    [chip wrap of currently selected, each removable             ]
    [MDRecycleView of filtered keys, each with MDCheckbox or
     a [- n +] cluster                                           ]
"""
from __future__ import annotations

from typing import Iterable

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.chip import MDChip, MDChipText, MDChipTrailingIcon
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from .option_widgets import OptionRow

__all__ = ("MassMultiSelectRow", "MassCounterRow", "ChecklistSelectRow")

ROW_HEIGHT = dp(40)
LIST_HEIGHT = dp(280)
LIST_HEIGHT_COMPACT = dp(200)


Builder.load_string(
    """
<MassRecycleView>:
    viewclass: 'MassSelectViewRow'
    bar_width: dp(8)
    RecycleBoxLayout:
        default_size: None, root.row_height
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: 'vertical'
        spacing: dp(2)

<MassCounterRecycleView>:
    viewclass: 'MassCounterViewRow'
    bar_width: dp(8)
    RecycleBoxLayout:
        default_size: None, root.row_height
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: 'vertical'
        spacing: dp(2)

<MassSelectViewRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(40)
    spacing: dp(8)
    padding: [dp(4), 0, dp(4), 0]
    MDCheckbox:
        id: cb
        size_hint: None, None
        size: dp(36), dp(36)
        pos_hint: {"center_y": 0.5}
        active: root.selected
        on_active: root.on_checkbox(self.active)
    MDLabel:
        text: root.label
        theme_text_color: "Primary"
        valign: "center"
        pos_hint: {"center_y": 0.5}

<MassCounterViewRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(40)
    spacing: dp(4)
    padding: [dp(4), 0, dp(4), 0]
    MDLabel:
        text: root.label
        size_hint_x: 0.5
        valign: "center"
        pos_hint: {"center_y": 0.5}
    MDIconButton:
        icon: 'minus'
        size_hint: None, None
        size: dp(36), dp(36)
        pos_hint: {"center_y": 0.5}
        on_release: root.bump(-1)
    MDTextField:
        id: field
        text: str(root.count)
        input_filter: 'int'
        size_hint_x: None
        width: dp(64)
        pos_hint: {"center_y": 0.5}
        on_text: root.set_count(self.text)
    MDIconButton:
        icon: 'plus'
        size_hint: None, None
        size: dp(36), dp(36)
        pos_hint: {"center_y": 0.5}
        on_release: root.bump(1)
    """
)


# ----- shared shell --------------------------------------------------------


class MassRecycleView(RecycleView):
    row_height = NumericProperty(ROW_HEIGHT)


class MassCounterRecycleView(RecycleView):
    row_height = NumericProperty(ROW_HEIGHT)


class MassSelectViewRow(RecycleDataViewBehavior, MDBoxLayout):
    label = StringProperty("")
    key = StringProperty("")
    selected = BooleanProperty(False)
    owner = ObjectProperty(None)

    def refresh_view_attrs(self, rv, index, data):
        self.owner = data.get("owner")
        return super().refresh_view_attrs(rv, index, data)

    def on_checkbox(self, active):
        # Keep the view property in step with the checkbox: recycling
        # only re-applies `selected` when the new data value differs from
        # the property, so a stale property would let the old `active`
        # survive onto another key's row.
        self.selected = active
        if self.owner is None:
            return
        self.owner._set_selected(self.key, active)


class MassCounterViewRow(RecycleDataViewBehavior, MDBoxLayout):
    label = StringProperty("")
    key = StringProperty("")
    count = NumericProperty(0)
    owner = ObjectProperty(None)

    def refresh_view_attrs(self, rv, index, data):
        self.owner = data.get("owner")
        return super().refresh_view_attrs(rv, index, data)

    def bump(self, delta):
        if self.owner is None:
            return
        new = max(0, int(self.count) + int(delta))
        self.count = new
        self.owner._set_count(self.key, new)

    def set_count(self, text):
        if self.owner is None:
            return
        try:
            new = max(0, int(text or 0))
        except ValueError:
            return
        if new != self.count:
            self.count = new
        self.owner._set_count(self.key, new)


# ----- MultiSelect (ItemSet / LocationSet) ---------------------------------


class MassMultiSelectRow(OptionRow):
    """Search field + RecycleView + chip stack of selections."""

    def __init__(self, descriptor: dict, world: dict, *, kind: str, **kwargs):
        super().__init__(descriptor, **kwargs)
        # Don't sort the full item/location list yet — that's the heavy
        # bit for ALTTP-scale worlds and `prepare_data()` does it on
        # first panel open. Stash the source so we can compute lazily.
        self._world = world
        self._kind = kind
        self._all_keys: list = []
        self._data_prepared = False

        default = descriptor.get("default") or []
        self._selected = set(default)
        self.value = sorted(self._selected)

        kind_hint = "items" if kind == "item" else "locations"

        # Search
        self._search = MDTextField(
            MDTextFieldHintText(text=f"Search {kind_hint}…"),
            size_hint_y=None,
            height=dp(48),
        )
        self._search.bind(text=lambda _i, t: self._refresh(t))
        self.add_widget(self._search)

        # Selected chips (cheap — only as many chips as the descriptor's
        # default selection, usually 0). Initialize `height` explicitly
        # so the parent OptionRow's `minimum_height` doesn't read the
        # Kivy `Widget.height` default (dp(100)) before our
        # `bind(minimum_height -> height)` settles — that race surfaced
        # as a ~100 px gap above every chip-bearing row.
        self._chip_wrap = MDStackLayout(
            spacing=dp(4),
            size_hint_y=None,
            height=dp(0),
            padding=[0, dp(4), 0, dp(4)],
        )
        self._chip_wrap.bind(minimum_height=self._chip_wrap.setter("height"))
        self.add_widget(self._chip_wrap)
        self._rebuild_chips()

        # RecycleView (empty until prepare_data fires).
        self._rv = MassRecycleView(size_hint_y=None, height=LIST_HEIGHT)
        self.add_widget(self._rv)

    def prepare_data(self):
        """Sort keys and fill the RecycleView. Called on first panel
        open via `OptionGroupPanel._prepare_rows` so we don't pay the
        sort + data-build cost during form construction."""
        if self._data_prepared:
            return
        self._all_keys = self._collect_keys(self.descriptor, self._world, self._kind)
        self._refresh("")
        self._data_prepared = True

    @staticmethod
    def _collect_keys(descriptor: dict, world: dict, kind: str) -> list:
        valid = descriptor.get("valid_keys")
        if valid:
            return sorted(valid)
        if kind == "item":
            return sorted(world.get("item_names") or [])
        return sorted(world.get("location_names") or [])

    def _refresh(self, query: str):
        q = (query or "").strip().lower()
        if q:
            keys = [k for k in self._all_keys if q in k.lower()]
        else:
            keys = self._all_keys
        # Cap visible rows; RecycleView is fast but rendering 5000 still
        # forces a giant layout pass we don't need.
        keys = keys[:500]
        self._rv.data = [
            {
                "label": k,
                "key": k,
                "selected": k in self._selected,
                "owner": self,
            }
            for k in keys
        ]

    def _set_selected(self, key: str, active: bool):
        if active:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self.value = sorted(self._selected)
        self._rebuild_chips()
        # Freshen the data entry in place so a recycled view row doesn't
        # reapply a stale `selected` — same guard as ChecklistSelectRow.
        for entry in self._rv.data:
            if entry["key"] == key:
                entry["selected"] = active
                break

    def apply_value(self, value):
        try:
            incoming = {str(v) for v in (value or [])}
        except TypeError:
            return  # not iterable — keep old state
        if self._data_prepared:
            # Keep only keys the world actually has; unknown names from
            # hand-edited YAML are silently dropped rather than crashing.
            selected = {k for k in self._all_keys if k in incoming}
        else:
            # prepare_data() hasn't sorted the real key list yet — accept
            # as-is, same as the __init__ default path. Recomputed once
            # prepare_data()/_refresh() runs against real keys.
            selected = incoming
        self._selected = selected
        self.value = sorted(self._selected)
        self._rebuild_chips()
        if self._data_prepared:
            self._refresh(self._search.text)

    def is_default(self) -> bool:
        return sorted(self.value or []) == sorted(self.descriptor.get("default") or [])

    def skip_when_default(self) -> bool:
        return True

    def _rebuild_chips(self):
        self._chip_wrap.clear_widgets()
        for key in sorted(self._selected):
            chip = MDChip(
                MDChipText(text=str(key)),
                MDChipTrailingIcon(icon="close"),
                type="input",
                size_hint=(None, None),
            )
            chip._option_key = key
            chip.bind(on_release=lambda _i, k=key: self._set_selected(k, False))
            self._chip_wrap.add_widget(chip)


# ----- Checklist (OptionSet) -----------------------------------------------


class ChecklistSelectRow(OptionRow):
    """Search + checkbox list + "N of M selected" summary, for
    option_sets with too many or too wordy keys for chips. No chip wrap
    by design: every child has a fixed height, so the row is
    width-independent and the expansion panel's height math stays exact.
    Unlike the Mass rows, option_set values always emit into YAML, so
    `skip_when_default` stays at the base False."""

    def __init__(self, descriptor: dict, **kwargs):
        super().__init__(descriptor, **kwargs)
        self._all_keys = sorted(str(k) for k in (descriptor.get("valid_keys") or []))
        self._selected = {str(k) for k in (descriptor.get("default") or [])}
        self.value = sorted(self._selected)

        self._search = MDTextField(
            MDTextFieldHintText(text="Search…"),
            size_hint_y=None,
            height=dp(48),
        )
        self._search.bind(text=lambda _i, t: self._refresh(t))
        self.add_widget(self._search)

        self._summary = MDLabel(
            text=self._summary_text(),
            theme_text_color="Secondary",
            size_hint_y=None,
            height=dp(24),
        )
        self.add_widget(self._summary)

        self._rv = MassRecycleView(size_hint_y=None, height=LIST_HEIGHT_COMPACT)
        self.add_widget(self._rv)
        self._refresh("")

    def _refresh(self, query: str):
        q = (query or "").strip().lower()
        if q:
            keys = [k for k in self._all_keys if q in k.lower()]
        else:
            # Selected first so the current picks are visible without
            # scrolling. Reorder only on query change — never on toggle —
            # so rows don't jump under the cursor.
            keys = [k for k in self._all_keys if k in self._selected] + [
                k for k in self._all_keys if k not in self._selected
            ]
        keys = keys[:500]
        self._rv.data = [
            {
                "label": k,
                "key": k,
                "selected": k in self._selected,
                "owner": self,
            }
            for k in keys
        ]

    def _set_selected(self, key: str, active: bool):
        if active:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self.value = sorted(self._selected)
        self._summary.text = self._summary_text()
        # Freshen the data entry in place (no refresh, no reorder) so a
        # recycled view row doesn't reapply a stale `selected` and
        # silently undo the toggle.
        for entry in self._rv.data:
            if entry["key"] == key:
                entry["selected"] = active
                break

    def apply_value(self, value):
        try:
            incoming = {str(v) for v in (value or [])}
        except TypeError:
            return  # not iterable — keep old state
        self._selected = {k for k in self._all_keys if k in incoming}
        self.value = sorted(self._selected)
        self._summary.text = self._summary_text()
        self._refresh(self._search.text)

    def is_default(self) -> bool:
        return sorted(self.value or []) == sorted(self.descriptor.get("default") or [])

    def _summary_text(self) -> str:
        return f"{len(self._selected)} of {len(self._all_keys)} selected"


# ----- Counter (Mass) ------------------------------------------------------


class MassCounterRow(OptionRow):
    """Like OptionCounterRow but RecycleView-backed."""

    def __init__(self, descriptor: dict, world: dict, **kwargs):
        super().__init__(descriptor, **kwargs)
        # Defer the keys sort + counts table for the same reason as
        # MassMultiSelectRow — item/location lists can be thousands of
        # entries. `prepare_data()` runs on first panel open.
        self._world = world
        self._all_keys: list = []
        self._data_prepared = False

        defaults = dict(descriptor.get("default") or {})
        # Only the user-defined non-zero defaults need to live in
        # `_counts` until prepare_data fills the rest with zeros.
        self._counts: dict = {k: int(v) for k, v in defaults.items()}
        self.value = self._nonzero_counts()

        self._search = MDTextField(
            MDTextFieldHintText(text="Search…"),
            size_hint_y=None,
            height=dp(48),
        )
        self._search.bind(text=lambda _i, t: self._refresh(t))
        self.add_widget(self._search)

        self._summary = MDLabel(
            text=self._summary_text(),
            theme_text_color="Secondary",
            size_hint_y=None,
            height=dp(24),
        )
        self.add_widget(self._summary)

        self._rv = MassCounterRecycleView(size_hint_y=None, height=LIST_HEIGHT)
        self.add_widget(self._rv)

    def prepare_data(self):
        if self._data_prepared:
            return
        if self.descriptor.get("verify_item_name"):
            self._all_keys = sorted(self._world.get("item_names") or [])
        else:
            self._all_keys = sorted(self._world.get("location_names") or [])
        # Backfill zeros for keys the user hasn't touched. `_counts`
        # already holds any non-zero defaults from __init__.
        for k in self._all_keys:
            self._counts.setdefault(k, 0)
        self._refresh("")
        self._data_prepared = True

    def _refresh(self, query: str):
        q = (query or "").strip().lower()
        if q:
            keys = [k for k in self._all_keys if q in k.lower()]
        else:
            # Show non-zero entries first when no query; otherwise top of list.
            nonzero = [k for k in self._all_keys if self._counts[k]]
            others = [k for k in self._all_keys if not self._counts[k]]
            keys = nonzero + others
        keys = keys[:500]
        self._rv.data = [
            {
                "label": k,
                "key": k,
                "count": self._counts[k],
                "owner": self,
            }
            for k in keys
        ]

    def _set_count(self, key: str, count: int):
        self._counts[key] = int(count)
        self.value = self._nonzero_counts()
        self._summary.text = self._summary_text()
        # Freshen the data entry in place so a recycled view row doesn't
        # redisplay the count it was built with.
        for entry in self._rv.data:
            if entry["key"] == key:
                entry["count"] = int(count)
                break

    def apply_value(self, value):
        if not isinstance(value, dict):
            return  # not a mapping — keep old state
        try:
            counts = {str(k): max(0, int(v)) for k, v in value.items()}
        except (TypeError, ValueError):
            return
        if self._data_prepared:
            # Full replace against the real key set: keys the incoming
            # value omits go back to zero; unknown keys are dropped.
            for key in self._all_keys:
                self._counts[key] = counts.get(key, 0)
        else:
            # prepare_data() hasn't backfilled zeros for the rest of the
            # world's keys yet — its setdefault() loop will do that later
            # without clobbering what we store here.
            self._counts = counts
        self.value = self._nonzero_counts()
        self._summary.text = self._summary_text()
        if self._data_prepared:
            self._refresh(self._search.text)

    def is_default(self) -> bool:
        default = {k: int(v) for k, v in (self.descriptor.get("default") or {}).items() if v}
        current = {k: int(v) for k, v in (self.value or {}).items() if v}
        return current == default

    def skip_when_default(self) -> bool:
        return True

    def _nonzero_counts(self) -> dict:
        return {k: v for k, v in self._counts.items() if v}

    def _summary_text(self) -> str:
        nonzero = sum(1 for v in self._counts.values() if v)
        return f"{nonzero} item(s) with non-zero count"
