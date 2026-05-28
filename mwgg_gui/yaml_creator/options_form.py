"""
Form containers — one widget per mode (Player Options / Weighted).

Container shape mirrors the hint screen (`mwgg_gui/hint/hintscreen.py`):

    MDScrollView (`_form_scroll`)
      └── MDList (= OptionsForm)
            ├── [WeightedPrimer]   (weighted form only)
            ├── OptionGroupPanel
            ├── OptionGroupPanel
            └── …

The form itself extends `MDList` so the scroll wraps it directly — no
extra MDBoxLayout in between. Panel construction is heavy (KH2 has
~45 options, ALTTP has hundreds of items per `OptionSet`), so the
form's `populate()` is a coroutine that awaits `asynckivy.sleep(0)`
between each panel. That yields the main thread back to the Clock so
`app.loading_layout`'s animation keeps rendering while the form
builds.

`YamlScreen` runs `asynckivy.start(form.populate())` once the worker
returns; `populate()` dispatches `on_ready` when the last panel is in
place. The screen drops the loading overlay on `on_ready`.

This module is deliberately worlds-free: the GUI process never imports
`worlds`, `Options`, or any apworld code. All option metadata reaches
us as plain JSON.
"""
from __future__ import annotations

import logging

import asynckivy
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.expansionpanel import (
    MDExpansionPanel,
    MDExpansionPanelContent,
    MDExpansionPanelHeader,
)
from kivymd.uix.list import MDList

from mwgg_gui.overrides.expansionlist import GameTrailingPressedIconButton

from .option_widgets import widget_for_option
from .weighted_widgets import WeightedPrimer, weight_widget_for_option

logger = logging.getLogger("Client")

__all__ = (
    "OptionsForm",
    "PlayerOptionsForm",
    "WeightedOptionsForm",
    "OptionGroupPanel",
    "OptionGroupHeader",
)


# KV mirrors `<-HintListPanel>` from `mwgg_gui/hint/hintscreen.py` —
# the dash strips kivymd's `<MDExpansionPanel>` rule so we own sizing
# end-to-end. We pair that with Python overrides of
# `_set_content_height` / `_update_original_content_height` below so
# we can bypass kivymd's buggy `content.height - dp(88)` math.
Builder.load_string(
    """
<-OptionGroupPanel>:
    orientation: 'vertical'
    size_hint_y: None
    height: self.minimum_height
    padding: dp(8), dp(4), dp(8), dp(4)
    MDExpansionPanelHeader:
        id: panel_header
        padding: dp(8), 0, dp(8), 0
        radius: dp(8), dp(8), dp(8), dp(8)
        size_hint_y: None
        height: dp(64)
    MDExpansionPanelContent:
        id: panel_content
        orientation: 'vertical'
        padding: dp(12), dp(8), dp(12), dp(12)
        spacing: dp(4)
        size_hint_y: None
        height: self.minimum_height

<OptionGroupHeader>:
    id: option_group_header
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(56)
    spacing: dp(4)
    padding: dp(8), dp(4), dp(8), dp(4)
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.secondaryContainerColor
    radius: dp(8)
    MDLabel:
        id: label
        text: root.text
        bold: True
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSecondaryContainerColor
        pos_hint: {"center_y": 0.5}
    GameTrailingPressedIconButton:
        id: chevron
        width: dp(40)
        icon: root.expand_icon
        pos_hint: {"center_y": 0.5, "center_x": 0.5}
        on_release: root.panel.toggle_expansion(self)
    """
)


# ----- header widget ------------------------------------------------------


class OptionGroupHeader(MDBoxLayout):
    """Label + chevron-style icon button that delegates expansion to the
    parent `OptionGroupPanel` via `panel.toggle_expansion(self)` — same
    pattern as `SlotListItemHeader` in `overrides/expansionlist.py`."""

    text = StringProperty("")
    expand_icon = StringProperty("gamepad-round-right")
    panel = ObjectProperty(None)


# ----- one panel per option group ----------------------------------------


class OptionGroupPanel(MDExpansionPanel):
    """Expansion panel for a single option group.

    Mirrors `GameListPanel` from `overrides/expansionlist.py`: subclass
    `MDExpansionPanel`, declare header + content in KV, and route the
    chevron's `on_release` through `toggle_expansion(self, chevron)`.
    """

    group_name = StringProperty("")
    panel_header: MDExpansionPanelHeader = ObjectProperty(None)
    panel_content: MDExpansionPanelContent = ObjectProperty(None)

    def __init__(
        self,
        group_name: str,
        descriptors: list,
        make_widget,
        on_value_changed,
        expand_icon: str = "gamepad-round-right",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.group_name = group_name
        self._descriptors = descriptors
        self._make_widget = make_widget
        self._on_value_changed = on_value_changed
        self._expand_icon = expand_icon
        self.row_widgets: dict = {}
        self.header_layout: OptionGroupHeader | None = None
        self._rows_prepared = False

    # -- height math overrides ---------------------------------------------
    #
    # kivymd's `MDExpansionPanel._set_content_height` caches
    # `_original_content_height = content.height - dp(88)`, which makes
    # the open animation animate to a height 88 px short of the actual
    # content — the bottom rows get clipped and visually overlap the
    # next panel's header. `HintListPanel` works around this by
    # overriding both hooks; we do the same with the simpler "use the
    # measured minimum_height" rule, since our content is a vertical
    # BoxLayout of rows whose heights sum cleanly.

    def _set_content_height(self, *args):
        if not self._content:
            return
        self._original_content_height = self._content.minimum_height
        self._content.height = 0

    def _update_original_content_height(self, _widget):
        if not self._content:
            return
        self._original_content_height = self._content.minimum_height

    async def populate(self):
        """Async populate. Caller awaits this from the form's own
        populate so the main loop ticks between rows."""
        self.panel_header = self.ids.panel_header
        self.panel_content = self.ids.panel_content

        header = OptionGroupHeader(
            text=self.group_name,
            expand_icon=self._expand_icon,
            panel=self,
        )
        self.panel_header.add_widget(header)
        self.header_layout = header
        await asynckivy.sleep(0)

        for desc in self._descriptors:
            await asynckivy.sleep(0)
            try:
                widget = self._make_widget(desc)
            except Exception as e:
                logger.warning(
                    "Failed to build widget for %s: %s",
                    desc.get("name"), e, exc_info=True,
                )
                continue
            widget.bind(on_value=self._on_value_changed)
            self.row_widgets[desc["name"]] = widget
            self.panel_content.add_widget(widget)

    def toggle_expansion(self, instance):
        """Toggle the panel + rotate the chevron. Same shape as
        `GameListPanel.toggle_expansion` in `overrides/expansionlist.py`.

        Note: `self.is_open` only flips to True after `open()`'s animation
        completes (see `MDExpansionPanel.open` in
        `kivymd/uix/expansionpanel/expansionpanel.py`). So inverting the
        chevron call against `self.is_open` here gives the correct visual
        — closed -> opening -> chevron rotates down.
        """
        if not self.is_open:
            self._prepare_rows()
            self.open()
        else:
            self.close()
        if self.is_open:
            self.set_chevron_up(instance)
        else:
            self.set_chevron_down(instance)

    def _prepare_rows(self):
        """Fire `prepare_data()` on any row that opted into lazy
        loading. Heavy item/location-name rows (MassMultiSelectRow,
        MassCounterRow) build their actual key list + RecycleView
        data here so the cost is paid once, when the user looks at
        the group, instead of during form construction.
        """
        if self._rows_prepared:
            return
        self._rows_prepared = True
        for widget in self.row_widgets.values():
            prepare = getattr(widget, "prepare_data", None)
            if callable(prepare):
                try:
                    prepare()
                except Exception as e:
                    logger.warning(
                        "prepare_data failed for %s: %s",
                        getattr(widget, "option_name", widget), e,
                    )


# ----- Base form -----------------------------------------------------------


class OptionsForm(MDList):
    """The scrollable form body — an `MDList` of `OptionGroupPanel`s
    (and optionally a leading `WeightedPrimer`).

    Built incrementally via the async `populate()` coroutine so the
    loading animation keeps playing while the panels mount. Dispatches:
      - `on_change(options)` whenever a row's value changes
      - `on_ready()` once when every panel is in place
    """

    __events__ = ("on_change", "on_ready")

    def __init__(self, world_data: dict, **kwargs):
        # `MDList` ships with size_hint_y=None already; mirror what
        # `hints_mdlist` does in hintscreen.py:236.
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("size_hint_x", 1)
        super().__init__(**kwargs)
        self.world_data = world_data
        self.game_name = world_data.get("game_name", "")
        self._world = world_data.get("world", {})
        self._groups = world_data.get("groups", {})
        self._panels: dict = {}

    # -- subclasses override -----------------------------------------------

    def _make_widget(self, descriptor: dict):
        raise NotImplementedError

    def _extras(self) -> list:
        """Optional widgets to prepend before the panels (e.g. the
        weighted-options primer card)."""
        return []

    # -- async population --------------------------------------------------

    async def populate(self):
        """Build the form incrementally so the loading overlay's
        animation keeps rendering throughout. Same pattern as
        `HintScreen.set_hints_list` (`mwgg_gui/hint/hintscreen.py:277`),
        but yields between every row — not just every panel — because a
        single option-set widget can build hundreds of chips on its own.
        """
        self.clear_widgets()
        self._panels.clear()

        await asynckivy.sleep(0)
        for extra in self._extras():
            self.add_widget(extra)
            await asynckivy.sleep(0)

        for group_name, descriptors in self._groups.items():
            if not descriptors:
                continue
            panel = OptionGroupPanel(
                group_name=group_name,
                descriptors=descriptors,
                make_widget=self._make_widget,
                on_value_changed=self._on_value_changed,
            )
            self._panels[group_name] = panel
            self.add_widget(panel)
            await asynckivy.sleep(0)
            # Each panel populates its own header + rows with yields
            # between every row.
            await panel.populate()

        # Option rows schedule `apply_default` on the next Clock tick;
        # yield once more so those have run before we claim ready.
        await asynckivy.sleep(0)
        self.dispatch("on_ready")

    # -- value plumbing ----------------------------------------------------

    def _on_value_changed(self, _instance, _value):
        logger.info(
            "yaml_creator: on_value from %s = %r",
            getattr(_instance, "option_name", _instance),
            _value,
        )
        self.dispatch("on_change", self.collect())

    def collect(self) -> dict:
        """Return {option_name: value} for every option except those
        whose row asks to be hidden when at default (item-name and
        location-name -valued options — the web's playerOptions YAML
        omits these unless the user customizes them, since dumping the
        full item/location list as a default is unreadable). Every
        other option emits with its current value so the YAML matches
        what the generator will actually see."""
        out: dict = {}
        for panel in self._panels.values():
            for name, widget in panel.row_widgets.items():
                try:
                    if widget.skip_when_default() and widget.is_default():
                        continue
                    out[name] = widget.value
                except Exception as e:
                    logger.warning("collect(): could not read %s: %s", name, e)
        return out

    def apply(self, options: dict):
        for name, value in (options or {}).items():
            widget = self._row_for(name)
            if widget is None:
                continue
            try:
                widget.value = value
            except Exception as e:
                logger.debug("apply(): %s rejected value: %s", name, e)

    def _row_for(self, name: str):
        for panel in self._panels.values():
            widget = panel.row_widgets.get(name)
            if widget is not None:
                return widget
        return None

    def on_change(self, options: dict):
        """Default handler — overridden via `bind(on_change=...)`."""

    def on_ready(self):
        """Default handler — overridden via `bind(on_ready=...)`."""


# ----- Player options form -------------------------------------------------


class PlayerOptionsForm(OptionsForm):
    def _make_widget(self, descriptor):
        return widget_for_option(descriptor, self._world)


# ----- Weighted (advanced) form -------------------------------------------


class WeightedOptionsForm(OptionsForm):
    def _extras(self) -> list:
        return [WeightedPrimer()]

    def _make_widget(self, descriptor):
        return weight_widget_for_option(descriptor)
