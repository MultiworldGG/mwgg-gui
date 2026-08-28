"""
Per-option-type row widgets for the Player Options form.

Each widget takes a *descriptor dict* (produced by `world_data.py`), not
a class object — the GUI process never imports the world's Options
module. Descriptor shape per type is documented in `world_data.py`.

Every widget extends `OptionRow` and exposes:
  - `option_name` : str
  - `value`       : kivy property reflecting the user's current pick;
    listeners subscribe with `bind(value=cb)` (see OptionRow)

Factory `widget_for_option(option_name, descriptor, world)` picks the
right class. `world` is the `data["world"]` dict (item/location names
and their groups); needed for Set / Counter rows when `valid_keys` is
empty and we have to fall back to the world's full name list.

Item-name and location-name -valued options always route to the
RecycleView-backed widgets in `mass_select.py` (any chip-per-key wrap
froze the loading animation for non-trivial item counts). Option sets
whose keys don't fit chips (see `_chips_fit`) route there too.

References:
  - WebHostLib/templates/playerOptions/macros.html — web equivalent
  - mwgg_gui/settings/settings_components.py — LabeledX row pattern
"""
from __future__ import annotations

import logging
from textwrap import wrap as textwrap_wrap
from typing import Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.chip import MDChip, MDChipText
from kivymd.uix.dropdownitem import MDDropDownItem, MDDropDownItemText
from kivymd.uix.expansionpanel import (
    MDExpansionPanel,
    MDExpansionPanelContent,
    MDExpansionPanelHeader,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.segmentedbutton import (
    MDSegmentedButton,
    MDSegmentedButtonItem,
)
from kivymd.uix.segmentedbutton.segmentedbutton import MDSegmentButtonLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.slider import MDSlider, MDSliderHandle, MDSliderValueLabel
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from kivymd.uix.tooltip import MDTooltip, MDTooltipPlain

logger = logging.getLogger("Client")

__all__ = (
    "OptionRow",
    "OptionTitle",
    "HelpIcon",
    "ToggleRow",
    "ChoiceRow",
    "TextChoiceRow",
    "RangeRow",
    "NamedRangeRow",
    "FreeTextRow",
    "OptionSetRow",
    "OptionCounterRow",
    "OptionDictRow",
    "widget_for_option",
)


# ----- KV ------------------------------------------------------------------

Builder.load_string(
    """
<OptionRow>:
    orientation: 'vertical'
    size_hint_y: None
    height: self.minimum_height
    padding: [dp(8), dp(4)]
    spacing: dp(2)

<OptionTitle>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(32)
    spacing: dp(4)
    MDLabel:
        id: label
        text: root.text
        theme_text_color: "Primary"
        size_hint_x: 1
    HelpIcon:
        id: help_icon
        icon: "help-circle-outline"
        tooltip_text: root.tooltip_text
        opacity: 1 if root.tooltip_text else 0

<HelpIcon>:
    size_hint: None, None
    size: dp(28), dp(28)
    pos_hint: {"center_y": 0.5}
    icon_size: dp(18)
    md_bg_color: 0, 0, 0, 0
    # kivymd's MDTooltip.add_widget (tooltip.py:521-528) intercepts an
    # MDTooltipPlain child and stashes it as the tooltip body. The
    # text must be pre-wrapped in Python (same approach as the
    # `list_tooltip` helper in overrides/expansionlist.py:209-229) —
    # MDLabel's `text_size`/`do_wrap` knobs don't behave reliably
    # inside a tooltip widget that ScaleBehavior is also animating.
    MDTooltipPlain:
        text: root.tooltip_text
        adaptive_height: True
        theme_text_color: "Custom"
        theme_bg_color: "Custom"
        md_bg_color: app.theme_cls.secondaryContainerColor
        text_color: app.theme_cls.onSecondaryContainerColor
    """
)


# ----- Title / tooltip -----------------------------------------------------


# Max chars per wrapped tooltip line. Matches the `list_tooltip` helper
# in overrides/expansionlist.py:209-229 (40 chars there); option
# docstrings are full sentences so we let them run a bit longer.
TOOLTIP_WRAP_WIDTH = 60


def _wrap_tooltip(text: str) -> str:
    """Pre-wrap a tooltip docstring. MDLabel's `text_size` / `do_wrap`
    don't behave reliably inside the tooltip widget (ScaleBehavior on
    MDTooltipPlain animates the bbox), so we mirror the
    `list_tooltip` approach: wrap in Python first, render multi-line.

    Preserves the docstring's own paragraph breaks (\\n\\n) by wrapping
    each paragraph independently. Single newlines inside a paragraph
    get folded into the wrap.
    """
    if not text:
        return ""
    out_paragraphs = []
    for paragraph in text.split("\n\n"):
        flat = " ".join(paragraph.split())
        if not flat:
            continue
        wrapped = textwrap_wrap(
            flat, width=TOOLTIP_WRAP_WIDTH, break_on_hyphens=False
        )
        out_paragraphs.append("\n".join(wrapped))
    return "\n\n".join(out_paragraphs)


class HelpIcon(MDTooltip, MDIconButton):
    """(?) icon with the option docstring shown on hover.

    `MDTooltip` MUST come first in the bases — `MDIconButton`'s chain
    pulls in `MDLabel` → `StateLayerBehavior`, whose `on_enter` (defined
    at `kivymd/uix/behaviors/state_layer_behavior.py:345`) does NOT
    call `super().on_enter()`. If `MDIconButton` is first in the MRO,
    `StateLayerBehavior.on_enter` wins and `MDTooltip.on_enter` is
    never invoked, so the tooltip never displays. Same ordering rule
    as `HintListItemLabel(ListItemTooltip, MDLabel)` and
    `ServerLabel(MDTooltip, MDTopAppBarTitle)`.
    """
    tooltip_text = StringProperty("")


class OptionTitle(MDBoxLayout):
    """Reusable title strip: `[label]               [?]`."""
    text = StringProperty("")
    tooltip_text = StringProperty("")


# ----- Base class ----------------------------------------------------------


class OptionRow(MDBoxLayout):
    """Base for every option row widget.

    `value` is a Kivy `ObjectProperty` — listeners subscribe with
    `bind(value=cb)` (callback gets `(instance, value)`). Kivy creates
    `on_<prop>` handlers only inside KV rules; a Python
    `bind(on_value=cb)` is silently dropped because no `on_value`
    event is registered.

    Subclasses should:
      * build their widget tree in `__init__` (no initial widget state)
      * set `self.value` in `__init__` so the form sees the default
        immediately
      * implement `apply_default()` to translate `self.value` into
        widget state (slider position, switch active, etc.)

    The base schedules `apply_default()` once on the next frame. This
    guarantees KivyMD's KV rules have applied to every child widget by
    the time we touch their properties — some kivymd widgets
    (`MDSwitch`, etc.) look up `self.ids` from their `on_<prop>`
    handlers, which would crash if invoked synchronously in `__init__`.
    """

    option_name = StringProperty("")
    display_name = StringProperty("")
    docstring = StringProperty("")
    value = ObjectProperty(None, allownone=True)

    def __init__(self, descriptor: dict, **kwargs):
        super().__init__(**kwargs)
        self.descriptor = descriptor
        self.option_name = descriptor.get("name", "")
        self.display_name = descriptor.get("display_name", self.option_name)
        self.docstring = descriptor.get("docstring", "")
        self.add_widget(
            OptionTitle(
                text=self.display_name,
                tooltip_text=_wrap_tooltip(self.docstring),
            )
        )
        Clock.schedule_once(self._apply_default_safely, 0)

    def _apply_default_safely(self, _dt):
        try:
            self.apply_default()
        except Exception as e:
            logger.warning(
                "apply_default(%s) failed: %s", self.option_name, e, exc_info=True
            )

    def apply_default(self):
        """Translate `self.value` into widget state. Called once on the
        frame after `__init__`. Override in subclasses; default is a
        no-op for rows that don't need post-KV widget state setup."""

    def apply_value(self, value):
        """Translate an externally-supplied `value` (Sync -> Form) into
        BOTH `self.value` and widget state. Unlike a bare `self.value =
        value` assignment, this must leave every internal (selected
        sets, counters, slider position, ...) consistent so the next
        user interaction doesn't recompute `value` from stale state and
        silently clobber the sync. Override in stateful subclasses;
        base is a plain passthrough for rows with no internal mirror of
        `value` (e.g. OptionDictRow). Tolerate bad/mismatched incoming
        values (EAFP: skip, keep old state) - sync must never crash on
        weird YAML."""
        self.value = value

    def is_default(self) -> bool:
        """Return True if `self.value` still matches the descriptor's
        default. Override for types whose `value` shape differs from
        the descriptor's `default` (Choice, sets, dicts)."""
        return self.value == self.descriptor.get("default")

    def skip_when_default(self) -> bool:
        """Return True to omit this option from collected YAML when
        the user hasn't changed it from default. The web's
        playerOptions UI omits item-name and location-name -valued
        options (start_inventory, exclude_locations, …) from generated
        YAML unless the user customized them — listing every item or
        location name as a default would make the YAML unreadable.
        All other options always emit so the YAML matches what the
        generator will actually see. Override in subclasses keyed off
        item/location names."""
        return False


# ----- Toggle --------------------------------------------------------------


class ToggleRow(OptionRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        self.value = bool(descriptor.get("default", 0))

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
        self._label = MDLabel(text="On" if self.value else "Off", size_hint_x=0.3)
        row.add_widget(self._label)
        self._switch = MDSwitch(pos_hint={"center_y": 0.5})
        self._switch.bind(active=self._on_active)
        row.add_widget(self._switch)
        self.add_widget(row)

    def apply_default(self):
        # Set after KV applies — MDSwitch.on_active touches self.ids.thumb.
        self._switch.active = bool(self.value)

    def apply_value(self, value):
        self.value = bool(value)
        self._switch.active = self.value
        self._label.text = "On" if self.value else "Off"

    def _on_active(self, _instance, active):
        self.value = bool(active)
        self._label.text = "On" if active else "Off"


# ----- Choice / TextChoice -------------------------------------------------


class ChoiceRow(OptionRow):
    """Segmented buttons if <=4 choices, dropdown otherwise.

    Descriptor keys:
        choices       : {key_str: machine_name}   (web YAML value)
        display_names : {key_str: human label}
        default       : the default key (int or str)
    """

    _SEGMENT_LIMIT = 4

    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        choices = self._readable_choices(descriptor)
        if not choices:
            self.add_widget(MDLabel(text="(no choices defined)"))
            return

        default = descriptor.get("default")
        # JSON forces string dict keys; coerce default to its string form
        # for the in-form value (we'll convert back at YAML emit time if
        # needed — most worlds accept the machine_name string in YAML).
        keys = [k for k, _machine, _label in choices]
        self._default_key = str(default) if str(default) in keys else keys[0]

        # The YAML value the user expects is the machine_name, not the
        # internal id. Store the machine_name as our value so it
        # serializes cleanly.
        machine_by_key = {k: m for k, m, _l in choices}
        self._machine_by_key = machine_by_key
        self.value = machine_by_key[self._default_key]

        if len(choices) <= self._SEGMENT_LIMIT:
            self._build_segmented(choices)
        else:
            self._build_dropdown(choices)

    @staticmethod
    def _readable_choices(descriptor):
        """Return [(key_str, machine_name, human_label), ...]."""
        choices = descriptor.get("choices") or {}
        display = descriptor.get("display_names") or {}
        return [
            (key, machine_name, display.get(key, machine_name))
            for key, machine_name in choices.items()
        ]

    def _build_segmented(self, choices):
        seg = MDSegmentedButton(size_hint_y=None, height=dp(40))
        self._items_by_key = {}
        for key, _machine, label in choices:
            item = MDSegmentedButtonItem(MDSegmentButtonLabel(text=label))
            item._option_key = key
            item.bind(active=self._on_segment_active)
            seg.add_widget(item)
            self._items_by_key[key] = item
        self.add_widget(seg)

    def _on_segment_active(self, instance, active):
        if active:
            self.value = self._machine_by_key[instance._option_key]

    def _build_dropdown(self, choices):
        self._label_by_key = {k: l for k, _m, l in choices}
        self._dropdown_item = MDDropDownItem(
            MDDropDownItemText(text=""),
            size_hint_y=None,
            height=dp(40),
        )
        self._dropdown_item.bind(on_release=lambda *_: self._open_menu())

        self._menu = MDDropdownMenu(
            caller=self._dropdown_item,
            items=[
                {
                    "text": label,
                    "on_release": (lambda k=key, l=label: self._pick(k, l)),
                }
                for key, _machine, label in choices
            ],
        )
        self.add_widget(self._dropdown_item)

    def apply_default(self):
        # Segmented: light up the default item — deferred because
        # MDSegmentedButtonItem.active uses kv-driven children to render.
        item = getattr(self, "_items_by_key", {}).get(getattr(self, "_default_key", None))
        if item is not None:
            item.active = True
        # Dropdown: set the visible label from the default key.
        if hasattr(self, "_dropdown_item") and hasattr(self, "_label_by_key"):
            self._dropdown_item.children[0].text = self._label_by_key.get(
                self._default_key, ""
            )

    def apply_value(self, value):
        machine_by_key = getattr(self, "_machine_by_key", None)
        if not machine_by_key:
            self.value = value
            return
        key = next((k for k, m in machine_by_key.items() if m == value), None)
        if key is None:
            return  # unknown value — keep old state
        self.value = value
        items_by_key = getattr(self, "_items_by_key", None)
        if items_by_key:
            # `MDSegmentedButtonItem.active` only deactivates siblings via
            # the widget's own on_release handler (a click) — a
            # programmatic `.active = True` here leaves the previously
            # active item lit unless we clear the others ourselves.
            for k, item in items_by_key.items():
                item.active = (k == key)
        if hasattr(self, "_dropdown_item") and hasattr(self, "_label_by_key"):
            self._dropdown_item.children[0].text = self._label_by_key.get(key, "")

    def is_default(self) -> bool:
        # Descriptor default is the option id (int); self.value is the
        # machine_name string. Compare via the lookup we built in init.
        default_machine = self._machine_by_key.get(self._default_key)
        return self.value == default_machine

    def _open_menu(self):
        self._menu.open()

    def _pick(self, key, label):
        self.value = self._machine_by_key[key]
        self._dropdown_item.children[0].text = label
        self._menu.dismiss()


class TextChoiceRow(ChoiceRow):
    """Like Choice, but allows a free-text 'Custom...' value."""

    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        self._custom_field = MDTextField(
            MDTextFieldHintText(text="Custom value"),
            size_hint_y=None,
            height=dp(48),
            opacity=0,
            disabled=True,
        )
        self._custom_field.bind(text=self._on_custom_text)
        self.add_widget(self._custom_field)
        if hasattr(self, "_menu"):
            self._menu.items.append(
                {"text": "Custom…", "on_release": self._enable_custom_mode}
            )

    def _enable_custom_mode(self):
        self._custom_field.opacity = 1
        self._custom_field.disabled = False
        self._custom_field.focus = True
        if hasattr(self, "_menu"):
            self._menu.dismiss()
        if hasattr(self, "_dropdown_item"):
            self._dropdown_item.children[0].text = "Custom…"

    def _on_custom_text(self, _instance, text):
        if text:
            self.value = text

    def apply_value(self, value):
        machine_by_key = getattr(self, "_machine_by_key", None)
        if machine_by_key and value in machine_by_key.values():
            self._custom_field.opacity = 0
            self._custom_field.disabled = True
            super().apply_value(value)
            return
        # Not one of the enumerated choices — treat as the custom value.
        self.value = value
        for item in getattr(self, "_items_by_key", {}).values():
            item.active = False
        self._custom_field.opacity = 1
        self._custom_field.disabled = False
        self._custom_field.text = str(value)
        if hasattr(self, "_dropdown_item"):
            self._dropdown_item.children[0].text = "Custom…"


# ----- Range / NamedRange --------------------------------------------------


class RangeRow(OptionRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        start = int(descriptor.get("range_start", 0))
        end = int(descriptor.get("range_end", 100))
        default = descriptor.get("default", start)
        try:
            default = int(default)
        except (TypeError, ValueError):
            default = start
        self.value = default
        self._range = (start, end)

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        self._slider = MDSlider(
            MDSliderHandle(),
            MDSliderValueLabel(),
            min=start,
            max=end,
            step=1,
            size_hint_x=0.75,
        )
        self._slider.bind(value=self._on_slider)

        self._number = MDTextField(
            size_hint_x=0.25,
            input_filter="int",
        )
        self._number.bind(text=self._on_text)

        row.add_widget(self._slider)
        row.add_widget(self._number)
        self.add_widget(row)

    def apply_default(self):
        # Setting slider.value fires _on_slider which also updates the
        # text field, so this single assignment covers both.
        self._slider.value = int(self.value)

    def apply_value(self, value):
        try:
            ival = int(value)
        except (TypeError, ValueError):
            return  # unparseable — keep old state
        start, end = self._range
        ival = max(start, min(end, ival))
        self.value = ival
        # Setting slider.value fires _on_slider, which also syncs the
        # text field — same cascade apply_default relies on.
        self._slider.value = ival

    def _on_slider(self, _instance, val):
        ival = int(val)
        self.value = ival
        if self._number.text != str(ival):
            self._number.text = str(ival)

    def _on_text(self, _instance, text):
        if not text:
            return
        try:
            ival = int(text)
        except ValueError:
            return
        start, end = self._range
        ival = max(start, min(end, ival))
        self.value = ival
        if int(self._slider.value) != ival:
            self._slider.value = ival


class NamedRangeRow(RangeRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        presets = dict(descriptor.get("special_range_names") or {})
        if not presets:
            return
        seg = MDSegmentedButton(size_hint_y=None, height=dp(40))
        for name, val in presets.items():
            item = MDSegmentedButtonItem(
                MDSegmentButtonLabel(text=name.replace("_", " ").title())
            )
            item._preset_value = int(val)
            item.bind(active=self._on_preset_active)
            seg.add_widget(item)
        self.add_widget(seg)

    def _on_preset_active(self, instance, active):
        if active:
            self.value = int(instance._preset_value)
            self._slider.value = int(instance._preset_value)
            self._number.text = str(int(instance._preset_value))


# ----- FreeText ------------------------------------------------------------


class FreeTextRow(OptionRow):
    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        self.value = str(descriptor.get("default", "") or "")
        self._field = MDTextField(
            MDTextFieldHintText(text="Enter value"),
            size_hint_y=None,
            height=dp(48),
        )
        self._field.bind(text=lambda _i, t: setattr(self, "value", t))
        self.add_widget(self._field)

    def apply_default(self):
        self._field.text = str(self.value)

    def apply_value(self, value):
        self.value = str(value) if value is not None else ""
        self._field.text = self.value


# ----- OptionSet / OptionList / small ItemSet, LocationSet -----------------


class _ChipMultiSelect(OptionRow):
    """Wrap of filter chips, one per key. Only used for small,
    short-labeled key sets (see `_chips_fit`); anything bigger routes
    to `ChecklistSelectRow` in mass_select.py."""

    def __init__(self, descriptor, keys, default_selected=None, **kwargs):
        super().__init__(descriptor, **kwargs)
        default_selected = set(default_selected or [])
        self.value = sorted(default_selected)
        self._selected = set(default_selected)
        self._chips_by_key: dict = {}
        # Guards _on_chip_active during apply_value's bulk chip.active
        # writes — those are just the visual echo of a self._selected we
        # already computed, not new user picks.
        self._applying_value = False

        # `height=dp(0)` before the bind — otherwise the parent's
        # minimum_height reads the Kivy Widget default (dp(100)) until
        # minimum_height first fires (same race as mass_select.py's
        # chip wrap).
        wrap = MDStackLayout(
            spacing=dp(4),
            size_hint_y=None,
            height=dp(0),
            padding=[0, dp(4), 0, dp(4)],
        )
        wrap.bind(minimum_height=wrap.setter("height"))
        for key in keys:
            chip = MDChip(
                MDChipText(text=str(key)),
                type="filter",
                size_hint=(None, None),
            )
            chip._option_key = key
            chip.bind(active=self._on_chip_active)
            wrap.add_widget(chip)
            self._chips_by_key[key] = chip
        self.add_widget(wrap)

    def apply_default(self):
        for key, chip in self._chips_by_key.items():
            if key in self._selected and not chip.active:
                chip.active = True

    def apply_value(self, value):
        try:
            incoming = set(value or [])
        except TypeError:
            return  # not iterable — keep old state
        selected = {
            key for key in self._chips_by_key
            if key in incoming or str(key) in incoming
        }
        self._selected = selected
        self.value = sorted(self._selected)
        self._applying_value = True
        try:
            for key, chip in self._chips_by_key.items():
                chip.active = key in self._selected
        finally:
            self._applying_value = False

    def is_default(self) -> bool:
        # Compare as sorted lists — chip order doesn't carry meaning,
        # and `self.value` is always sorted.
        return sorted(self.value or []) == sorted(self.descriptor.get("default") or [])

    def _on_chip_active(self, instance, active):
        if self._applying_value:
            return
        if active:
            self._selected.add(instance._option_key)
        else:
            self._selected.discard(instance._option_key)
        self.value = sorted(self._selected)


class OptionSetRow(_ChipMultiSelect):
    def __init__(self, descriptor, **kwargs):
        keys = sorted(descriptor.get("valid_keys") or [])
        default = descriptor.get("default") or []
        super().__init__(descriptor, keys, default_selected=default, **kwargs)


# ----- OptionCounter -------------------------------------------------------


class OptionCounterRow(OptionRow):
    """A list of [label | - | n | +] rows. `value` is a dict {key: int}."""

    def __init__(self, descriptor, world, **kwargs):
        super().__init__(descriptor, **kwargs)
        keys = _counter_keys(descriptor, world)
        defaults = dict(descriptor.get("default") or {})
        self.value = {k: int(defaults.get(k, 0)) for k in keys}
        self._counts = dict(self.value)
        self._fields_by_key: dict = {}

        col = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            # `height=0` before the bind — an empty col never dispatches
            # minimum_height, leaving the dp(100) Widget default.
            height=0,
            spacing=dp(2),
        )
        col.bind(minimum_height=col.setter("height"))
        for key in keys:
            col.add_widget(self._make_row(key))
        self.add_widget(col)

    def _make_row(self, key):
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
        row.add_widget(MDLabel(text=str(key), size_hint_x=0.55))
        minus = MDIconButton(icon="minus", size_hint_x=None, width=dp(36))
        field = MDTextField(
            input_filter="int",
            size_hint_x=None,
            width=dp(64),
        )
        plus = MDIconButton(icon="plus", size_hint_x=None, width=dp(36))

        self._fields_by_key[key] = field
        minus.bind(on_release=lambda *_: self._bump(key, field, -1))
        plus.bind(on_release=lambda *_: self._bump(key, field, +1))
        field.bind(text=lambda _i, t, k=key: self._set(k, t))

        row.add_widget(minus)
        row.add_widget(field)
        row.add_widget(plus)
        return row

    def apply_default(self):
        for key, field in self._fields_by_key.items():
            field.text = str(self._counts.get(key, 0))

    def apply_value(self, value):
        if not isinstance(value, dict):
            return  # not a mapping — keep old state
        counts = {}
        for key in self._fields_by_key:
            try:
                counts[key] = max(0, int(value.get(key, 0)))
            except (TypeError, ValueError):
                counts[key] = self._counts.get(key, 0)
        self._counts = counts
        self.value = dict(self._counts)
        for key, field in self._fields_by_key.items():
            field.text = str(self._counts.get(key, 0))

    def is_default(self) -> bool:
        # Drop zero counts on both sides — those are the same as "not
        # mentioned" in the YAML.
        default = {k: int(v) for k, v in (self.descriptor.get("default") or {}).items() if v}
        current = {k: int(v) for k, v in (self.value or {}).items() if v}
        return current == default

    def skip_when_default(self) -> bool:
        # Counters that index by item or location name are the
        # `start_inventory` / `item_links` shape — defaults shouldn't
        # appear in the YAML (the full item/location list would be
        # noise). Counters with an explicit `valid_keys` use a small,
        # option-defined key set and stay in the YAML so the user can
        # see the shape.
        d = self.descriptor
        return bool(d.get("verify_item_name") or d.get("verify_location_name"))

    def _bump(self, key, field, delta):
        new = max(0, self._counts[key] + delta)
        self._counts[key] = new
        field.text = str(new)
        self.value = dict(self._counts)

    def _set(self, key, text):
        try:
            new = max(0, int(text or 0))
        except ValueError:
            return
        self._counts[key] = new
        self.value = dict(self._counts)


# ----- OptionDict (manual-config card) -------------------------------------


class OptionDictRow(OptionRow):
    """The web punts on OptionDict; so do we."""

    def __init__(self, descriptor, **kwargs):
        super().__init__(descriptor, **kwargs)
        self.value = dict(descriptor.get("default") or {})
        msg = MDLabel(
            text=(
                "This option is a dictionary. Edit it directly in the YAML "
                "pane on the right — the form can't safely represent its "
                "structure."
            ),
            theme_text_color="Secondary",
            size_hint_y=None,
        )
        msg.bind(texture_size=lambda _i, s: setattr(msg, "height", s[1] + dp(8)))
        self.add_widget(msg)

    def is_default(self) -> bool:
        return (self.value or {}) == (self.descriptor.get("default") or {})


# ----- Factory -------------------------------------------------------------


def widget_for_option(descriptor: dict, world: dict) -> OptionRow:
    """Return the right widget for an option descriptor."""
    t = descriptor.get("type", "free_text")

    try:
        if t == "toggle":
            return ToggleRow(descriptor)
        if t == "text_choice":
            return TextChoiceRow(descriptor)
        if t == "choice":
            return ChoiceRow(descriptor)
        if t == "named_range":
            return NamedRangeRow(descriptor)
        if t == "range":
            return RangeRow(descriptor)
        if t == "free_text":
            return FreeTextRow(descriptor)

        # Item-name and location-name -valued options always go to the
        # RecycleView-backed widgets — building a chip-per-key wrap
        # froze the loading animation for any world with >50ish items,
        # and even small lists are smoother as a virtualized list.
        if t == "item_set":
            from .mass_select import MassMultiSelectRow
            return MassMultiSelectRow(descriptor, world, kind="item")
        if t == "location_set":
            from .mass_select import MassMultiSelectRow
            return MassMultiSelectRow(descriptor, world, kind="location")
        if t == "option_set":
            keys = [str(k) for k in (descriptor.get("valid_keys") or [])]
            if _chips_fit(keys):
                return OptionSetRow(descriptor)
            from .mass_select import ChecklistSelectRow
            return ChecklistSelectRow(descriptor)

        if t == "option_counter":
            if descriptor.get("verify_item_name") or descriptor.get("verify_location_name"):
                from .mass_select import MassCounterRow
                return MassCounterRow(descriptor, world)
            return OptionCounterRow(descriptor, world)

        if t == "option_dict":
            return OptionDictRow(descriptor)
    except Exception as e:
        logger.warning(
            "widget_for_option: unable to build widget for %s (type=%s): %s",
            descriptor.get("name"), t, e,
        )

    return FreeTextRow(descriptor)


# ----- helpers -------------------------------------------------------------


CHIP_MAX_KEYS = 15
CHIP_MAX_LABEL_WORDS = 2
CHIP_MAX_LABEL_CHARS = 24


def _chips_fit(keys) -> bool:
    """Chips only for small sets of short labels; wordy keys (OoT's
    dungeon names, trick descriptions) wrap into an unusable chip wall
    and route to `ChecklistSelectRow` instead."""
    return len(keys) <= CHIP_MAX_KEYS and all(
        len(k.split()) <= CHIP_MAX_LABEL_WORDS and len(k) <= CHIP_MAX_LABEL_CHARS
        for k in keys
    )


def _counter_keys(descriptor: dict, world: dict):
    # Only used by `OptionCounterRow` now. Item-name and
    # location-name -valued counters route to `MassCounterRow` in the
    # factory, so the verify_item_name / verify_location_name fallbacks
    # only fire when somebody hand-constructs `OptionCounterRow` and
    # the descriptor happens to need them — defensive.
    valid = descriptor.get("valid_keys")
    if valid:
        return sorted(valid)
    if descriptor.get("verify_item_name"):
        return sorted(world.get("item_names") or [])
    if descriptor.get("verify_location_name"):
        return sorted(world.get("location_names") or [])
    return []
