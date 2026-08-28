"""
Weighted-options form: one flat RecycleView over every group/option.

The form owns pure models (`weighted_model.py`) and renders them
through a single RecycleView, so only the visible rows exist as
widgets regardless of world size (a widget stack per option melts down
at OoT scale).

Recycled rows are stateless views: every weight lives in the model and
is echoed into `rv.data` in place (the RecycleView cannot preserve
per-widget toggles; a recycled row always rebuilds from its data
entry, and the YAML sync path restores through `apply` the same way).

Row types, dispatched via `key_viewclass`:
  WeightGroupRow:        group header; tap toggles the group open
  WeightOptionHeaderRow: option name + help tooltip + most-likely text
  WeightValueRow:        one candidate value's weight slider
  WeightCustomRow:       add-a-custom-value field (text/range types)
  WeightDirectRow:       summary row for direct-value options
                         (supports_weighting false: set/dict/counter
                         family); tap opens the player-mode widget in
                         a dialog and writes the result back

`self_scrolling = True` tells YamlScreen to host the form directly in
the pixel-sized scroll box: a RecycleView owns its own viewport and
must not sit inside the shared MDScrollView.
"""
from __future__ import annotations

import logging

import asynckivy
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.slider import MDSlider, MDSliderHandle, MDSliderValueLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from .option_widgets import HelpIcon, _wrap_tooltip, widget_for_option
from .weighted_model import DirectOptionModel, model_for_option

logger = logging.getLogger("Client")

__all__ = (
    "WeightedOptionsForm",
    "WeightedPrimer",
)

GROUP_ROW_H = dp(56)
OPTION_ROW_H = dp(52)
VALUE_ROW_H = dp(40)
CUSTOM_ROW_H = dp(48)
DIRECT_ROW_H = dp(56)


Builder.load_string(
    """
<WeightedRV>:
    viewclass: 'WeightValueRow'
    RecycleBoxLayout:
        key_viewclass: 'viewclass'
        key_size: 'size'
        default_size: None, dp(40)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: 'vertical'
        spacing: dp(2)
        padding: [dp(4), dp(4), dp(4), dp(8)]

<WeightGroupRow>:
    orientation: 'horizontal'
    spacing: dp(4)
    padding: [dp(12), dp(4), dp(12), dp(4)]
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.secondaryContainerColor
    radius: dp(8)
    MDLabel:
        text: root.text
        bold: True
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSecondaryContainerColor
        pos_hint: {"center_y": 0.5}
    MDIcon:
        icon: "gamepad-round-down" if root.expanded else "gamepad-round-right"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSecondaryContainerColor
        pos_hint: {"center_y": 0.5}
        size_hint_x: None
        width: dp(40)

<WeightOptionHeaderRow>:
    orientation: 'horizontal'
    spacing: dp(4)
    padding: [dp(12), dp(2), dp(8), 0]
    MDBoxLayout:
        orientation: 'vertical'
        MDLabel:
            text: root.display
            bold: True
            theme_text_color: "Primary"
            shorten: True
            shorten_from: 'right'
        MDLabel:
            text: root.likely
            theme_text_color: "Secondary"
            shorten: True
            shorten_from: 'right'
    HelpIcon:
        icon: "help-circle-outline"
        tooltip_text: root.tooltip
        opacity: 1 if root.tooltip else 0

<WeightValueRow>:
    orientation: 'horizontal'
    spacing: dp(6)
    padding: [dp(20), 0, dp(8), 0]
    MDLabel:
        text: root.label
        size_hint_x: 0.30
        theme_text_color: "Primary"
        shorten: True
        shorten_from: 'right'
        pos_hint: {"center_y": 0.5}
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
        icon: 'close'
        size_hint_x: None
        width: dp(36)
        pos_hint: {"center_y": 0.5}
        opacity: 1 if root.removable else 0
        disabled: not root.removable
        on_release: root.request_delete()

<WeightCustomRow>:
    orientation: 'horizontal'
    spacing: dp(6)
    padding: [dp(20), dp(2), dp(8), dp(2)]
    MDTextField:
        id: field
        text: root.text
        size_hint_x: 0.85
        on_text: root.on_field_text(self.text)
        on_text_validate: root.submit()
        MDTextFieldHintText:
            text: root.hint
    MDIconButton:
        icon: 'plus'
        size_hint_x: None
        width: dp(40)
        pos_hint: {"center_y": 0.5}
        on_release: root.submit()

<WeightDirectRow>:
    orientation: 'horizontal'
    spacing: dp(4)
    padding: [dp(12), dp(2), dp(8), dp(2)]
    MDBoxLayout:
        orientation: 'vertical'
        MDLabel:
            text: root.display
            bold: True
            theme_text_color: "Primary"
            shorten: True
            shorten_from: 'right'
        MDLabel:
            text: root.summary
            theme_text_color: "Secondary"
            shorten: True
            shorten_from: 'right'
    HelpIcon:
        icon: "help-circle-outline"
        tooltip_text: root.tooltip
        opacity: 1 if root.tooltip else 0
    MDIcon:
        icon: 'pencil-outline'
        theme_text_color: "Secondary"
        pos_hint: {"center_y": 0.5}
        size_hint_x: None
        width: dp(32)
        opacity: 1 if root.editable else 0

<WeightedPrimer>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(6)
    size_hint_y: None
    height: self.minimum_height
    radius: dp(10)
    elevation: 1
    MDBoxLayout:
        orientation: 'horizontal'
        size_hint_y: None
        height: dp(32)
        MDLabel:
            text: "How weighted options work"
            bold: True
            theme_text_color: "Primary"
            pos_hint: {"center_y": 0.5}
        MDIconButton:
            icon: "chevron-down" if root.expanded else "chevron-right"
            size_hint: None, None
            size: dp(32), dp(32)
            pos_hint: {"center_y": 0.5}
            on_release: root.expanded = not root.expanded

<PrimerBullet>:
    theme_text_color: "Secondary"
    size_hint_y: None
    text_size: self.width, None
    height: self.texture_size[1]
    """
)


# ----- primer card ---------------------------------------------------------


class PrimerBullet(MDLabel):
    pass


_PRIMER_BULLETS = (
    "One YAML, many possible games. Weighted options randomize what your "
    "next game looks like, not what's inside it.",
    "Higher weight = more likely. Think of weights as raffle tickets. "
    "Weight 25 vs weight 5 means 5x more likely to be picked.",
    "Weights are per option, not per item. Setting goal: kill_ganon to 50 "
    "means every game picks one goal; individual items in that game "
    "aren't split by these weights.",
    "Zero means never; anything > 0 is in the pool. A single non-zero "
    "weight pins the option to that value.",
)


class WeightedPrimer(MDCard):
    """Collapsible explainer card rendered above the RecycleView."""

    expanded = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
            # `height=0` before the bind; see the chip-wrap sizing note
            # in mass_select.py.
            height=0,
        )
        self._body.bind(minimum_height=self._body.setter("height"))
        for text in _PRIMER_BULLETS:
            self._body.add_widget(PrimerBullet(text=text))
        if self.expanded:
            self.add_widget(self._body)

    def on_expanded(self, _instance, expanded):
        if expanded and self._body.parent is None:
            self.add_widget(self._body)
        elif not expanded and self._body.parent is not None:
            self.remove_widget(self._body)


# ----- view rows -----------------------------------------------------------


class _WeightedViewRow(RecycleDataViewBehavior):
    """Shared recycling plumbing. `_refreshing` gates the write-back
    handlers while data is being (re)applied to a recycled view: the KV
    bindings echo data properties into live widgets (slider value, field
    text) whose change events would otherwise write stale values into
    whatever model the row previously displayed."""

    form = ObjectProperty(None, allownone=True)
    option = StringProperty("")

    index = None
    _refreshing = False

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self._refreshing = True
        try:
            return super().refresh_view_attrs(rv, index, data)
        finally:
            self._refreshing = False


class WeightGroupRow(_WeightedViewRow, ButtonBehavior, MDBoxLayout):
    text = StringProperty("")
    group = StringProperty("")
    expanded = BooleanProperty(False)

    def on_release(self):
        if self.form:
            self.form.toggle_group(self.group)


class WeightOptionHeaderRow(_WeightedViewRow, MDBoxLayout):
    display = StringProperty("")
    likely = StringProperty("")
    tooltip = StringProperty("")


class WeightValueRow(_WeightedViewRow, MDBoxLayout):
    key = StringProperty("")
    label = StringProperty("")
    weight = NumericProperty(0)
    removable = BooleanProperty(False)

    def on_slider(self, value):
        if self._refreshing:
            return
        # The view property must stay in step: recycling only re-applies
        # `weight` when the incoming data value differs from it.
        self.weight = int(value)
        if self.form:
            self.form.on_weight_row(self.index, self.option, self.key, int(value))

    def request_delete(self):
        if self.form and self.removable:
            self.form.remove_custom(self.option, self.key)


class WeightCustomRow(_WeightedViewRow, MDBoxLayout):
    hint = StringProperty("")
    text = StringProperty("")

    def on_field_text(self, text):
        if self._refreshing:
            return
        self.text = text
        if self.form:
            self.form.store_custom_text(self.index, self.option, text)

    def submit(self):
        if self.form and self.form.submit_custom(self.index, self.option, self.text):
            self.text = ""


class WeightDirectRow(_WeightedViewRow, ButtonBehavior, MDBoxLayout):
    display = StringProperty("")
    summary = StringProperty("")
    tooltip = StringProperty("")
    editable = BooleanProperty(True)

    def on_release(self):
        if self.form and self.editable:
            self.form.open_direct_editor(self.option)


class WeightedRV(RecycleView):
    pass


# ----- the form ------------------------------------------------------------


class WeightedOptionsForm(MDBoxLayout):
    """Primer + RecycleView. API-compatible with `OptionsForm`
    (`populate` / `collect` / `apply` / `option_names`, plus the
    `on_change` / `on_ready` events) so YamlScreen drives both form
    kinds identically."""

    __events__ = ("on_change", "on_ready")

    self_scrolling = True

    def __init__(self, world_data: dict, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", dp(4))
        super().__init__(**kwargs)
        self.world_data = world_data
        self.game_name = world_data.get("game_name", "")
        self._world = world_data.get("world", {})
        self._groups = world_data.get("groups", {})
        self._models: dict = {}
        self._group_models: dict = {}
        self._expanded: set = set()
        # Option name -> rv.data index of its header/summary row, for
        # in-place refreshes of the most-likely / summary text.
        self._header_index: dict = {}
        self._suppress_change = True

        self.add_widget(WeightedPrimer())
        self._rv = WeightedRV()
        self.add_widget(self._rv)

    # -- population ---------------------------------------------------------

    async def populate(self):
        """Build the models (pure dicts, cheap even at OoT scale) and
        the initial row data. Async for interface parity with
        OptionsForm.populate: the loading overlay animation gets a frame
        between groups."""
        for group_name, descriptors in self._groups.items():
            models = []
            for desc in descriptors or []:
                try:
                    model = model_for_option(desc, self._world)
                except Exception as e:
                    logger.warning(
                        "Failed to build model for %s: %s",
                        desc.get("name"), e, exc_info=True,
                    )
                    continue
                models.append(model)
                self._models[model.name] = model
            if models:
                self._group_models[group_name] = models
            await asynckivy.sleep(0)
        self._rebuild_data()
        self._suppress_change = False
        self.dispatch("on_ready")

    def _rebuild_data(self):
        rows: list = []
        self._header_index.clear()
        for group_name, models in self._group_models.items():
            expanded = group_name in self._expanded
            rows.append({
                "viewclass": "WeightGroupRow",
                "size": (None, GROUP_ROW_H),
                "text": group_name,
                "group": group_name,
                "expanded": expanded,
                "form": self,
            })
            if not expanded:
                continue
            for model in models:
                self._header_index[model.name] = len(rows)
                if isinstance(model, DirectOptionModel):
                    rows.append({
                        "viewclass": "WeightDirectRow",
                        "size": (None, DIRECT_ROW_H),
                        "display": model.display_name,
                        "summary": model.summary_text(),
                        "tooltip": _wrap_tooltip(model.docstring),
                        "editable": model.editable,
                        "option": model.name,
                        "form": self,
                    })
                    continue
                rows.append({
                    "viewclass": "WeightOptionHeaderRow",
                    "size": (None, OPTION_ROW_H),
                    "display": model.display_name,
                    "likely": model.most_likely_text(),
                    "tooltip": _wrap_tooltip(model.docstring),
                    "option": model.name,
                    "form": self,
                })
                for entry in model.entries:
                    rows.append({
                        "viewclass": "WeightValueRow",
                        "size": (None, VALUE_ROW_H),
                        "option": model.name,
                        "key": entry.key,
                        "label": entry.label,
                        "weight": model.weights.get(entry.key, 0),
                        "removable": entry.removable,
                        "form": self,
                    })
                if model.custom_hint:
                    rows.append({
                        "viewclass": "WeightCustomRow",
                        "size": (None, CUSTOM_ROW_H),
                        "option": model.name,
                        "hint": model.custom_hint,
                        "text": "",
                        "form": self,
                    })
        self._rv.data = rows

    # -- row callbacks ------------------------------------------------------

    def toggle_group(self, group_name: str):
        if group_name in self._expanded:
            self._expanded.discard(group_name)
        else:
            self._expanded.add(group_name)
        self._rebuild_data()

    def on_weight_row(self, index, option: str, key: str, weight: int):
        model = self._models.get(option)
        if model is None:
            return
        model.set_weight(key, weight)
        self._freshen(index, "WeightValueRow", option, "weight", int(weight), key=key)
        self._refresh_likely(option)
        self._notify_change()

    def store_custom_text(self, index, option: str, text: str):
        # Freshen the data entry in place so a recycled add-value row
        # restores in-progress text instead of blanking it.
        self._freshen(index, "WeightCustomRow", option, "text", text)

    def submit_custom(self, index, option: str, text: str) -> bool:
        """Returns True when the field should clear (added or already
        present); False leaves the text for the user to fix."""
        model = self._models.get(option)
        if model is None:
            return False
        before = len(getattr(model, "entries", ()))
        key = model.add_custom(text)
        if key is None:
            return False
        if len(model.entries) != before:
            self._rebuild_data()
            self._notify_change()
        else:
            self._freshen(index, "WeightCustomRow", option, "text", "")
        return True

    def remove_custom(self, option: str, key: str):
        model = self._models.get(option)
        if model is None or not model.remove(key):
            return
        self._rebuild_data()
        self._notify_change()

    def _freshen(self, index, viewclass: str, option: str, field: str, value, key=None):
        """Silently update one rv.data entry in place (no refresh, no
        reorder) so a recycled view doesn't reapply stale state and
        undo the user's change; same guard as mass_select.py. The
        viewclass/option/key checks make a stale index (data rebuilt
        under a live view) a no-op instead of a cross-row write."""
        data = self._rv.data
        if index is None or not 0 <= index < len(data):
            return
        entry = data[index]
        if entry.get("viewclass") != viewclass or entry.get("option") != option:
            return
        if key is not None and entry.get("key") != key:
            return
        entry[field] = value

    def _refresh_likely(self, option: str):
        model = self._models.get(option)
        idx = self._header_index.get(option)
        data = self._rv.data
        if model is None or idx is None or not 0 <= idx < len(data):
            return
        if data[idx].get("option") != option:
            return
        text = model.most_likely_text()
        # In-place data writes don't refresh a displayed row; poke the
        # live view too, if this header is currently on screen.
        data[idx]["likely"] = text
        view = self._rv.view_adapter.get_visible_view(idx)
        if view is not None and getattr(view, "option", None) == option:
            view.likely = text

    # -- direct-value dialog ------------------------------------------------

    def open_direct_editor(self, option: str):
        """Host the player-mode widget for a direct-value option in a
        dialog; its edits write straight back into the model (and the
        live preview) via the value binding."""
        model = self._models.get(option)
        if model is None or not getattr(model, "editable", False):
            return
        try:
            widget = widget_for_option(model.descriptor, self._world)
        except Exception as e:
            logger.warning("direct editor for %s failed to build: %s", option, e)
            return
        prepare = getattr(widget, "prepare_data", None)
        if callable(prepare):
            try:
                prepare()
            except Exception as e:
                logger.warning("prepare_data failed for %s: %s", option, e)
        try:
            widget.apply_value(model.value)
        except Exception as e:
            logger.debug("direct editor %s rejected value: %s", option, e)
        widget.bind(value=lambda _i, v: self._on_direct_value(option, v))

        scroll = MDScrollView(
            size_hint_y=None,
            do_scroll_x=False,
            height=min(dp(480), max(dp(200), Window.height - dp(280))),
        )
        scroll.add_widget(widget)
        dialog = MDDialog(
            MDDialogHeadlineText(text=model.display_name),
            MDDialogContentContainer(scroll, orientation="vertical"),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Done"),
                    on_release=lambda *_: dialog.dismiss(),
                ),
                spacing=dp(8),
            ),
        )
        dialog.state_press = 0
        dialog.open()

    def _on_direct_value(self, option: str, value):
        model = self._models.get(option)
        if not isinstance(model, DirectOptionModel):
            return
        model.value = value
        idx = self._header_index.get(option)
        data = self._rv.data
        if idx is not None and 0 <= idx < len(data) and data[idx].get("option") == option:
            text = model.summary_text()
            data[idx]["summary"] = text
            view = self._rv.view_adapter.get_visible_view(idx)
            if view is not None and getattr(view, "option", None) == option:
                view.summary = text
        self._notify_change()

    # -- OptionsForm-compatible API -----------------------------------------

    def collect(self) -> dict:
        out: dict = {}
        for models in self._group_models.values():
            for model in models:
                try:
                    if model.skip_when_default() and model.is_default():
                        continue
                    out[model.name] = model.value
                except Exception as e:
                    logger.warning("collect(): could not read %s: %s", model.name, e)
        return out

    def apply(self, options: dict):
        self._suppress_change = True
        try:
            changed = False
            for name, value in (options or {}).items():
                model = self._models.get(name)
                if model is None:
                    continue
                try:
                    changed = model.apply_value(value) or changed
                except Exception as e:
                    logger.debug("apply(): %s rejected value: %s", name, e)
            if changed:
                self._rebuild_data()
        finally:
            self._suppress_change = False

    def option_names(self) -> set:
        return set(self._models.keys())

    def _notify_change(self):
        if self._suppress_change:
            return
        self.dispatch("on_change", self.collect())

    def on_change(self, options: dict):
        """Default handler; overridden via `bind(on_change=...)`."""

    def on_ready(self):
        """Default handler; overridden via `bind(on_ready=...)`."""
