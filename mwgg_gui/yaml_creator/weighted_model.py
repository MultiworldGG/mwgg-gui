"""
Pure data models for the weighted-options form.

The weighted form renders through a RecycleView, so no widget may own
option state: recycled rows rebuild from data and would silently revert
anything stored on the widget. Every weight table lives here instead;
`weighted_form.py` echoes it into RecycleView data and the YAML sync
path restores it via `apply_value`.

No kivy imports; unit-tested directly in tests/test_weighted_model.py.

`value` for a weighted model is a dict {value_label: weight_int}. The
web sets weights as integers 0..50; we keep the same scale so YAML
output matches.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

__all__ = (
    "WEIGHT_MIN",
    "WEIGHT_MAX",
    "WEIGHT_DEFAULT",
    "WeightEntry",
    "WeightedOptionModel",
    "DirectOptionModel",
    "model_for_option",
)

WEIGHT_MIN = 0
WEIGHT_MAX = 50
WEIGHT_DEFAULT = 25


class WeightEntry(NamedTuple):
    key: str
    label: str
    removable: bool


# ----- weightable options ---------------------------------------------------


class WeightedOptionModel:
    """One weightable option's weight table.

    `entries` is the display order; `weights` maps entry key -> weight in
    the same insertion order, so `value` serializes in display order.
    """

    # Hint text for the add-a-custom-value control; None = no control.
    custom_hint: Optional[str] = None

    def __init__(self, descriptor: dict):
        self.descriptor = descriptor
        self.name = descriptor.get("name", "")
        self.display_name = descriptor.get("display_name", self.name)
        self.docstring = descriptor.get("docstring", "")
        self.entries: list[WeightEntry] = []
        self.weights: dict[str, int] = {}
        self._build(descriptor)
        self._initial_weights = {str(k): int(v) for k, v in self.weights.items()}

    def _build(self, descriptor: dict):
        raise NotImplementedError

    def _add(self, key, label: str, *, weight: int = 0, removable: bool = False):
        key = str(key)
        if key in self.weights:
            return
        self.entries.append(WeightEntry(key, label, removable))
        self.weights[key] = int(weight)

    # -- form-facing API ----------------------------------------------------

    @property
    def value(self) -> dict:
        return {str(k): int(v) for k, v in self.weights.items()}

    def set_weight(self, key: str, weight: int):
        if key in self.weights:
            self.weights[key] = max(WEIGHT_MIN, min(WEIGHT_MAX, int(weight)))

    def add_custom(self, text: str) -> Optional[str]:
        """Validate and add a user-typed value row. Returns the (added or
        already-present) key, or None when the text is empty/invalid so
        the caller can leave the field for the user to fix."""
        text = (text or "").strip()
        if not text:
            return None
        key = self._coerce_custom_key(text)
        if key is None:
            return None
        if key in self.weights:
            return key
        self._add(key, key, weight=WEIGHT_DEFAULT, removable=True)
        return key

    def _coerce_custom_key(self, text: str) -> Optional[str]:
        return text

    def remove(self, key: str) -> bool:
        if not any(e.key == key and e.removable for e in self.entries):
            return False
        self.entries = [e for e in self.entries if e.key != key]
        self.weights.pop(key, None)
        return True

    def apply_value(self, value) -> bool:
        """Sync -> model: `value` is {label: weight}. Returns True when
        applied (the row set may have changed and the caller rebuilds
        the view). A bad or mismatched value returns False and keeps
        the old state."""
        if not isinstance(value, dict):
            return False
        try:
            weights = {str(k): int(v) for k, v in value.items()}
        except (TypeError, ValueError):
            return False
        for key in self.weights:
            self.weights[key] = weights.get(key, 0)
        # Keys present in the incoming value but not one of our built-in
        # rows (a custom text/range entry from a previous session) get a
        # new removable row, same as the add-value control.
        for key, weight in weights.items():
            if key not in self.weights and weight:
                self._add(key, key, weight=weight, removable=True)
        return True

    def is_default(self) -> bool:
        """True while every weight matches the state `_build` produced."""
        current = {str(k): int(v) for k, v in self.weights.items()}
        return current == self._initial_weights

    def skip_when_default(self) -> bool:
        return False

    def most_likely_text(self) -> str:
        nonzero = {k: v for k, v in self.weights.items() if v > 0}
        if not nonzero:
            return "Most likely: none (all weights zero)"
        total = sum(nonzero.values())
        key, weight = max(nonzero.items(), key=lambda kv: kv[1])
        if len(nonzero) == 1:
            return f"Locked to {key}"
        pct = int(round(100 * weight / total))
        return f"Most likely: {key} ({pct}%)"


class ToggleWeights(WeightedOptionModel):
    def _build(self, d):
        default = bool(d.get("default", 0))
        self._add("false", "No", weight=0 if default else WEIGHT_DEFAULT)
        self._add("true", "Yes", weight=WEIGHT_DEFAULT if default else 0)
        self._add("random", "Random")


class ChoiceWeights(WeightedOptionModel):
    def _build(self, d):
        default = d.get("default")
        display = d.get("display_names") or {}
        for key, machine_name in (d.get("choices") or {}).items():
            label = display.get(key, machine_name)
            self._add(
                machine_name,
                label,
                weight=WEIGHT_DEFAULT if str(default) == str(key) else 0,
            )
        self._add("random", "Random")


class TextChoiceWeights(ChoiceWeights):
    custom_hint = "custom value"


class RangeWeights(WeightedOptionModel):
    custom_hint = "integer value"

    def _build(self, d):
        start = int(d.get("range_start", 0))
        end = int(d.get("range_end", 100))
        default = d.get("default", start)
        try:
            default = int(default)
        except (TypeError, ValueError):
            default = start
        self._range = (start, end)
        self._default = default

        # An endpoint default weights its own row; without this the
        # stack starts all-zero and the generator can't roll it.
        self._add(str(start), str(start), weight=WEIGHT_DEFAULT if default == start else 0)
        if start < default < end:
            self._add(str(default), str(default), weight=WEIGHT_DEFAULT, removable=True)
        self._add(str(end), str(end), weight=WEIGHT_DEFAULT if default == end != start else 0)
        for key, name in (
            ("random", "Random"),
            ("random-low", "Random (Low)"),
            ("random-middle", "Random (Middle)"),
            ("random-high", "Random (High)"),
        ):
            self._add(key, name)

    def _coerce_custom_key(self, text: str) -> Optional[str]:
        try:
            n = int(text)
        except ValueError:
            return None
        start, end = self._range
        if start <= n <= end:
            return str(n)
        return None


class NamedRangeWeights(RangeWeights):
    def _build(self, d):
        super()._build(d)
        # A named range's default may be a special value outside
        # range_start..range_end; that name's row carries the default
        # weight so the stack isn't all-zero.
        default_assigned = any(self.weights.values())
        for name, val in (d.get("special_range_names") or {}).items():
            try:
                matches_default = not default_assigned and int(val) == self._default
            except (TypeError, ValueError):
                matches_default = False
            self._add(
                name,
                f"{name.replace('_', ' ').title()} ({val})",
                weight=WEIGHT_DEFAULT if matches_default else 0,
            )
            default_assigned = default_assigned or matches_default


class FreeTextWeights(WeightedOptionModel):
    custom_hint = "custom value"

    def _build(self, d):
        default = d.get("default") or ""
        if default:
            self._add(str(default), str(default), weight=WEIGHT_DEFAULT, removable=True)


# ----- direct-value options -------------------------------------------------


class DirectOptionModel:
    """Options the generator consumes as direct values (`supports_weighting`
    false: the set/dict/counter family). A {value: weight} stack would be
    misparsed (wrong seeds or OptionError), so these keep player-mode
    semantics. The form shows a summary row; tapping it edits the value in
    a dialog hosting the player-mode widget. Value shapes, `is_default`,
    and `skip_when_default` mirror option_widgets.py / mass_select.py."""

    def __init__(self, descriptor: dict, world: dict):
        self.descriptor = descriptor
        self.world = world or {}
        self.name = descriptor.get("name", "")
        self.display_name = descriptor.get("display_name", self.name)
        self.docstring = descriptor.get("docstring", "")
        self.type = descriptor.get("type", "free_text")
        # The web punts on OptionDict; so do we (YAML-pane edits only).
        self.editable = self.type != "option_dict"
        self.value = self._default_value()

    def _mass_counter(self) -> bool:
        d = self.descriptor
        return bool(d.get("verify_item_name") or d.get("verify_location_name"))

    def _counter_keys(self) -> list:
        d = self.descriptor
        valid = d.get("valid_keys")
        if valid:
            return sorted(str(k) for k in valid)
        if d.get("verify_item_name"):
            return sorted(self.world.get("item_names") or [])
        if d.get("verify_location_name"):
            return sorted(self.world.get("location_names") or [])
        return []

    def _default_value(self):
        d = self.descriptor
        default = d.get("default")
        if self.type in ("item_set", "location_set", "option_set"):
            return sorted(str(v) for v in (default or []))
        if self.type == "option_counter":
            counts = {str(k): int(v) for k, v in (default or {}).items()}
            if self._mass_counter():
                # start_inventory/item_links shape: only non-zero counts
                # are meaningful (matches MassCounterRow._nonzero_counts).
                return {k: v for k, v in counts.items() if v}
            return {k: counts.get(k, 0) for k in self._counter_keys()}
        if self.type == "option_dict":
            return dict(default or {})
        return default

    def apply_value(self, value) -> bool:
        if self.type in ("item_set", "location_set", "option_set"):
            try:
                incoming = sorted({str(v) for v in (value or [])})
            except TypeError:
                return False
            if self.type == "option_set":
                valid = {str(k) for k in (self.descriptor.get("valid_keys") or [])}
                incoming = sorted(v for v in incoming if v in valid)
            self.value = incoming
            return True
        if self.type == "option_counter":
            if not isinstance(value, dict):
                return False
            try:
                counts = {str(k): max(0, int(v)) for k, v in value.items()}
            except (TypeError, ValueError):
                return False
            if self._mass_counter():
                self.value = {k: v for k, v in counts.items() if v}
            else:
                self.value = {k: counts.get(k, 0) for k in self._counter_keys()}
            return True
        if self.type == "option_dict":
            if not isinstance(value, dict):
                return False
            self.value = dict(value)
            return True
        self.value = value
        return True

    def is_default(self) -> bool:
        d = self.descriptor
        if self.type in ("item_set", "location_set", "option_set"):
            return sorted(self.value or []) == sorted(
                str(v) for v in (d.get("default") or [])
            )
        if self.type == "option_counter":
            default = {str(k): int(v) for k, v in (d.get("default") or {}).items() if v}
            current = {str(k): int(v) for k, v in (self.value or {}).items() if v}
            return current == default
        if self.type == "option_dict":
            return (self.value or {}) == (d.get("default") or {})
        return self.value == d.get("default")

    def skip_when_default(self) -> bool:
        # Item-name and location-name -valued options stay out of the
        # YAML at default (the full name list would be noise). Counters
        # with explicit valid_keys keep defaults visible so the user
        # sees the shape (matches the web playerOptions behavior).
        if self.type in ("item_set", "location_set"):
            return True
        if self.type == "option_counter":
            return self._mass_counter()
        return False

    def summary_text(self) -> str:
        if self.type in ("item_set", "location_set", "option_set"):
            return f"{len(self.value or [])} selected (tap to edit)"
        if self.type == "option_counter":
            nonzero = sum(1 for v in (self.value or {}).values() if v)
            return f"{nonzero} with non-zero count (tap to edit)"
        if self.type == "option_dict":
            return "Dictionary option: edit in the YAML pane"
        return f"{self.value} (tap to edit)"


# ----- factory -------------------------------------------------------------


# Types the generator consumes as direct values: Generate.handle_option
# feeds options with `supports_weighting = False` (the set/dict/counter
# family) their raw YAML value via from_any, with no weighted pick. Used
# as the routing fallback for payloads too old to carry the
# `supports_weighting` field.
_DIRECT_VALUE_TYPES = frozenset({
    "item_set",
    "location_set",
    "option_set",
    "option_counter",
    "option_dict",
})


def model_for_option(descriptor: dict, world: dict):
    t = descriptor.get("type", "free_text")
    supports_weighting = descriptor.get("supports_weighting")
    if supports_weighting is None:
        supports_weighting = t not in _DIRECT_VALUE_TYPES
    if not supports_weighting:
        return DirectOptionModel(descriptor, world)
    if t == "toggle":
        return ToggleWeights(descriptor)
    if t == "text_choice":
        return TextChoiceWeights(descriptor)
    if t == "choice":
        return ChoiceWeights(descriptor)
    if t == "named_range":
        return NamedRangeWeights(descriptor)
    if t == "range":
        return RangeWeights(descriptor)
    if t == "free_text":
        return FreeTextWeights(descriptor)
    # Unrecognized weightable type; free text keeps it editable.
    return FreeTextWeights(descriptor)
