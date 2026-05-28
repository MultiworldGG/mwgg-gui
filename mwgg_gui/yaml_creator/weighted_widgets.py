"""
Weighted-options rows (the "advanced" page).

Each option becomes a stack of weight rows. The chosen value at
generation time is picked proportional to the weights. The web sets
weights as integers 0..50; we keep the same scale so YAML output
matches.

`value` for a weighted row is a dict {value_label: weight_int}.

`weight_widget_for_option(descriptor)` picks the right row type given
an option descriptor produced by `worker.py`.

A `WeightedPrimer` widget (separate `MDCard`) is rendered once at the
top of the weighted form to explain the raffle metaphor.
"""
from __future__ import annotations

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.chip import MDChip, MDChipText
from kivymd.uix.label import MDLabel
from kivymd.uix.slider import MDSlider, MDSliderHandle, MDSliderValueLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from .option_widgets import OptionRow

__all__ = (
    "WeightedRow",
    "WeightedPrimer",
    "weight_widget_for_option",
)

WEIGHT_MIN = 0
WEIGHT_MAX = 50
WEIGHT_DEFAULT = 25


Builder.load_string(
    """
<WeightRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(40)
    spacing: dp(6)
    MDLabel:
        text: root.label
        size_hint_x: 0.30
        theme_text_color: "Primary"
    MDSlider:
        id: slider
        min: 0
        max: 50
        step: 1
        value: root.weight
        size_hint_x: 0.55
        on_value: root.on_slider(self.value)
        MDSliderHandle:
        MDSliderValueLabel:
    MDIconButton:
        id: delete_btn
        icon: 'close'
        size_hint_x: None
        width: dp(36)
        opacity: 1 if root.removable else 0
        disabled: not root.removable
        on_release: root.request_delete()

<WeightedPrimer>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(6)
    size_hint_y: None
    height: self.minimum_height
    radius: dp(10)
    elevation: 1
    MDLabel:
        text: "How weighted options work"
        bold: True
        theme_text_color: "Primary"
        size_hint_y: None
        height: dp(24)
    PrimerBullet:
        text: "One YAML, many possible games. Weighted options randomize what your next game looks like — not what's inside it."
    PrimerBullet:
        text: "Higher weight = more likely. Think of weights as raffle tickets. Weight 25 vs weight 5 means 5× more likely to be picked."
    PrimerBullet:
        text: "Weights are per option, not per item. Setting goal: kill_ganon to 50 means every game picks one goal — individual items in that game aren't split by these weights."
    PrimerBullet:
        text: "Zero means never; anything > 0 is in the pool. A single non-zero weight pins the option to that value."

<PrimerBullet@MDLabel>:
    theme_text_color: "Secondary"
    size_hint_y: None
    text_size: self.width, None
    height: self.texture_size[1]
    """
)


# ----- single weight row ---------------------------------------------------


class WeightRow(MDBoxLayout):
    label = StringProperty("")
    weight = NumericProperty(WEIGHT_DEFAULT)
    removable = ObjectProperty(False)
    owner = ObjectProperty(None)
    key = ObjectProperty(None)

    def on_slider(self, value):
        self.weight = int(value)
        if self.owner:
            self.owner._on_weight_change(self.key, int(value))

    def request_delete(self):
        if self.owner:
            self.owner._remove_row(self.key)


# ----- weighted option row (base) ------------------------------------------


class WeightedRow(OptionRow):
    """Container for one option's weight stack. Subclasses populate the
    initial rows and (optionally) provide an "Add value" control."""

    def __init__(self, descriptor: dict, **kwargs):
        super().__init__(descriptor, **kwargs)
        self._weights: dict = {}
        self._row_widgets: dict = {}

        # Always-visible docstring on the weighted page.
        if self.docstring:
            doc_label = MDLabel(
                text=self.docstring,
                theme_text_color="Secondary",
                size_hint_y=None,
            )
            doc_label.bind(
                texture_size=lambda _i, s: setattr(doc_label, "height", s[1] + dp(4))
            )
            self.add_widget(doc_label)

        self._rows_container = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(2),
        )
        self._rows_container.bind(
            minimum_height=self._rows_container.setter("height")
        )
        self.add_widget(self._rows_container)

        self._likely_chip = MDChip(
            MDChipText(text="Most likely: —"),
            type="assist",
            size_hint=(None, None),
        )
        self.add_widget(self._likely_chip)

    # --- API used by subclasses --------------------------------------------

    def _add_row(self, key, label: str, *, weight: int = 0, removable: bool = False):
        if key in self._row_widgets:
            return
        row = WeightRow(
            label=label,
            weight=weight,
            removable=removable,
            owner=self,
            key=key,
        )
        self._rows_container.add_widget(row)
        self._row_widgets[key] = row
        self._weights[key] = weight
        self._refresh_value()

    def _remove_row(self, key):
        row = self._row_widgets.pop(key, None)
        if row is not None:
            self._rows_container.remove_widget(row)
        self._weights.pop(key, None)
        self._refresh_value()

    def _on_weight_change(self, key, weight):
        self._weights[key] = int(weight)
        self._refresh_value()

    def is_default(self) -> bool:
        """A weighted option is at default when the user hasn't touched
        any slider since the subclass populated the initial rows. The
        subclass calls `_snapshot_default_weights()` at the end of its
        own __init__ to capture that state."""
        snapshot = getattr(self, "_initial_weights", None)
        if snapshot is None:
            return False
        current = {str(k): int(v) for k, v in self._weights.items()}
        expected = {str(k): int(v) for k, v in snapshot.items()}
        return current == expected

    def _snapshot_default_weights(self):
        """Subclasses call this after their initial `_add_row` calls so
        `is_default` has something to compare against."""
        self._initial_weights = {str(k): int(v) for k, v in self._weights.items()}

    def _refresh_value(self):
        self.value = {str(k): int(v) for k, v in self._weights.items()}
        self._likely_chip.children[0].text = self._most_likely_text()

    def _most_likely_text(self) -> str:
        nonzero = {k: v for k, v in self._weights.items() if v > 0}
        if not nonzero:
            return "Most likely: — (all weights zero)"
        total = sum(nonzero.values())
        key, weight = max(nonzero.items(), key=lambda kv: kv[1])
        pct = int(round(100 * weight / total))
        if len(nonzero) == 1:
            return f"Locked to {key}"
        return f"Most likely: {key} ({pct}%)"


# ----- Toggle --------------------------------------------------------------


class WeightedToggleRow(WeightedRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        default = bool(descriptor.get("default", 0))
        self._add_row("false", "No", weight=0 if default else WEIGHT_DEFAULT)
        self._add_row("true", "Yes", weight=WEIGHT_DEFAULT if default else 0)
        self._add_row("random", "Random", weight=0)
        self._snapshot_default_weights()


# ----- Choice / TextChoice -------------------------------------------------


class WeightedChoiceRow(WeightedRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        default = descriptor.get("default")
        choices = descriptor.get("choices") or {}
        display = descriptor.get("display_names") or {}
        for key, machine_name in choices.items():
            label = display.get(key, machine_name)
            self._add_row(
                machine_name,
                label,
                weight=WEIGHT_DEFAULT if str(default) == str(key) else 0,
            )
        self._add_row("random", "Random", weight=0)
        self._snapshot_default_weights()


class WeightedTextChoiceRow(WeightedChoiceRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        self._add_custom_value_controls("custom value")
        self._snapshot_default_weights()


# ----- Range / NamedRange --------------------------------------------------


class WeightedRangeRow(WeightedRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        start = int(descriptor.get("range_start", 0))
        end = int(descriptor.get("range_end", 100))
        default = descriptor.get("default", start)
        try:
            default = int(default)
        except (TypeError, ValueError):
            default = start
        self._range = (start, end)

        self._add_row(str(start), f"{start}", weight=0, removable=False)
        if start < default < end:
            self._add_row(str(default), f"{default}", weight=WEIGHT_DEFAULT, removable=True)
        self._add_row(str(end), f"{end}", weight=0, removable=False)
        for key, name in {
            "random": "Random",
            "random-low": "Random (Low)",
            "random-middle": "Random (Middle)",
            "random-high": "Random (High)",
        }.items():
            self._add_row(key, name, weight=0)
        self._add_custom_value_controls("integer value")
        self._snapshot_default_weights()

    def _coerce_custom_key(self, text: str):
        try:
            n = int(text)
        except ValueError:
            return None
        start, end = self._range
        if start <= n <= end:
            return str(n)
        return None


class WeightedNamedRangeRow(WeightedRangeRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        for name, val in (descriptor.get("special_range_names") or {}).items():
            self._add_row(name, f"{name.replace('_', ' ').title()} ({val})", weight=0)
        self._snapshot_default_weights()


# ----- FreeText ------------------------------------------------------------


class WeightedFreeTextRow(WeightedRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        default = descriptor.get("default") or ""
        if default:
            self._add_row(str(default), str(default), weight=WEIGHT_DEFAULT, removable=True)
        self._add_custom_value_controls("custom value")
        self._snapshot_default_weights()


# ----- Add-value control --------------------------------------------------


def _add_custom_value_controls(self: WeightedRow, hint: str):
    row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(6))
    field = MDTextField(
        MDTextFieldHintText(text=hint),
        size_hint_x=0.85,
    )
    btn = MDIconButton(icon="plus", size_hint_x=None, width=dp(40))

    def _add(*_):
        text = (field.text or "").strip()
        if not text:
            return
        key = text
        if hasattr(self, "_coerce_custom_key"):
            coerced = self._coerce_custom_key(text)
            if coerced is None:
                return
            key = coerced
        if key in self._row_widgets:
            field.text = ""
            return
        self._add_row(key, key, weight=WEIGHT_DEFAULT, removable=True)
        field.text = ""

    btn.bind(on_release=_add)
    field.bind(on_text_validate=_add)
    row.add_widget(field)
    row.add_widget(btn)
    self.add_widget(row)


WeightedRow._add_custom_value_controls = _add_custom_value_controls


# ----- Primer card ---------------------------------------------------------


class WeightedPrimer(MDCard):
    pass


# ----- factory -------------------------------------------------------------


def weight_widget_for_option(descriptor: dict) -> WeightedRow:
    t = descriptor.get("type", "free_text")
    if t == "toggle":
        return WeightedToggleRow(descriptor)
    if t == "text_choice":
        return WeightedTextChoiceRow(descriptor)
    if t == "choice":
        return WeightedChoiceRow(descriptor)
    if t == "named_range":
        return WeightedNamedRangeRow(descriptor)
    if t == "range":
        return WeightedRangeRow(descriptor)
    if t == "free_text":
        return WeightedFreeTextRow(descriptor)
    # Set/Dict/Counter options aren't weighted on the web — fall through.
    return WeightedFreeTextRow(descriptor)
