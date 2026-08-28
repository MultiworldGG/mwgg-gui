"""
Form containers - one widget per mode (Player Options / Weighted).

Container shape mirrors the hint screen (`mwgg_gui/hint/hintscreen.py`):

    MDScrollView (`_form_scroll`)
      └── MDList (= OptionsForm)
            ├── [WeightedPrimer]   (weighted form only)
            ├── OptionGroupPanel
            ├── OptionGroupPanel
            └── ...

The form extends `MDList` so the scroll wraps it directly. Panel
construction is heavy (KH2 ~45 options, ALTTP hundreds of items per
`OptionSet`), so `populate()` is a coroutine awaiting
`asynckivy.sleep(0)` between steps, keeping the loading animation
rendering; it dispatches `on_ready` when the last panel is in place and
the screen then drops the overlay. NOTE: sleep(0) may need to be
higher; the animation is still choppy between panels.

Deliberately worlds-free: the GUI process never imports `worlds`,
`Options`, or any apworld code; option metadata arrives as plain JSON.
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


# The `<-` prefix strips kivymd's `<MDExpansionPanel>` rule so we own
# sizing (mirrors `<-HintListPanel>`); paired with the height overrides below.
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
    parent `OptionGroupPanel` via `panel.toggle_expansion(self)` - same
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
        self.bind(on_open=self._resync_content_height)

    # -- height math overrides ---------------------------------------------
    #
    # kivymd caches `_original_content_height = content.height - dp(88)`,
    # so the open animation lands 88 px short and clips the bottom rows;
    # both hooks are overridden to use the measured minimum_height.

    def _set_content_height(self, *args):
        if not self._content:
            return
        self._original_content_height = self._content.minimum_height
        self._content.height = 0

    def _update_original_content_height(self, _widget):
        if not self._content:
            return
        self._original_content_height = self._content.minimum_height

    def _resync_content_height(self, *_args):
        # Pre-open, kivymd keeps the content detached, so it measures at
        # the 100 px default width and chip wraps inflate minimum_height;
        # re-measure once the open animation completes at real width.
        content = self._content
        if not content:
            return
        self._original_content_height = content.minimum_height
        if self.is_open:
            content.height = content.minimum_height

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
            # Bind the property: Kivy silently drops `bind(on_value=...)` (see OptionRow).
            widget.bind(value=self._on_value_changed)
            self.row_widgets[desc["name"]] = widget
            self.panel_content.add_widget(widget)

    def toggle_expansion(self, instance):
        """Toggle the panel + rotate the chevron (same shape as
        `GameListPanel.toggle_expansion`). `is_open` flips only after the
        open animation completes, so testing it inverted gives the correct
        chevron direction."""
        if not self.is_open:
            self._prepare_rows()
            # kivymd captures the target once, 0.8 s after construction; refresh or reflows leave it stale.
            self._update_original_content_height(None)
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
    """The scrollable form body: an `MDList` of `OptionGroupPanel`s
    (and optionally a leading `WeightedPrimer`).

    Built incrementally via the async `populate()` coroutine so the
    loading animation keeps playing while the panels mount. Dispatches:
      - `on_change(options)` whenever a row's value changes
      - `on_ready()` once when every panel is in place
    """

    __events__ = ("on_change", "on_ready")

    def __init__(self, world_data: dict, **kwargs):
        # MDList ships size_hint_y=None already; mirrors hints_mdlist (hintscreen.py:236).
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("size_hint_x", 1)
        super().__init__(**kwargs)
        self.world_data = world_data
        self.game_name = world_data.get("game_name", "")
        self._world = world_data.get("world", {})
        self._groups = world_data.get("groups", {})
        self._panels: dict = {}
        # Suppress dispatch during programmatic writes (build, Sync -> Form) so only user edits reach on_change.
        self._suppress_change = True

    # -- subclasses override -----------------------------------------------

    def _make_widget(self, descriptor: dict):
        raise NotImplementedError

    def _extras(self) -> list:
        """Optional widgets to prepend before the panels (e.g. the
        weighted-options primer card)."""
        return []

    # -- async population --------------------------------------------------

    async def populate(self):
        """Build incrementally so the loading animation keeps rendering
        (same pattern as `HintScreen.set_hints_list`); yields between every
        row because one option-set widget can build hundreds of chips."""
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
            # panel.populate() itself yields between rows.
            await panel.populate()

        # Rows schedule apply_default next tick; yield once more before claiming ready.
        await asynckivy.sleep(0)
        self._suppress_change = False
        self.dispatch("on_ready")

    # -- value plumbing ----------------------------------------------------

    def _on_value_changed(self, _instance, _value):
        if self._suppress_change:
            return
        self.dispatch("on_change", self.collect())

    def collect(self) -> dict:
        """Return {option_name: value}, omitting rows hidden at default
        (item/location-name options, mirroring the web's playerOptions
        YAML)."""
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
        # Suppressed: an on_change here would re-render the preview over the text Sync -> Form just applied.
        self._suppress_change = True
        try:
            for name, value in (options or {}).items():
                widget = self._row_for(name)
                if widget is None:
                    continue
                try:
                    # apply_value also updates internal state and visuals (see OptionRow).
                    widget.apply_value(value)
                except Exception as e:
                    logger.debug("apply(): %s rejected value: %s", name, e)
        finally:
            self._suppress_change = False

    def _row_for(self, name: str):
        for panel in self._panels.values():
            widget = panel.row_widgets.get(name)
            if widget is not None:
                return widget
        return None

    def option_names(self) -> set:
        """Names of every option the form currently owns a row for. The
        preview pane uses this to tell real options apart from
        hand-written game-section keys it must preserve."""
        names: set = set()
        for panel in self._panels.values():
            names.update(panel.row_widgets.keys())
        return names

    def on_change(self, options: dict):
        """Default handler; overridden via `bind(on_change=...)`."""

    def on_ready(self):
        """Default handler; overridden via `bind(on_ready=...)`."""


# ----- Player options form -------------------------------------------------


class PlayerOptionsForm(OptionsForm):
    def _make_widget(self, descriptor):
        return widget_for_option(descriptor, self._world)


# ----- Weighted (advanced) form -------------------------------------------


class WeightedOptionsForm(OptionsForm):
    def _extras(self) -> list:
        return [WeightedPrimer()]

    def _make_widget(self, descriptor):
        return weight_widget_for_option(descriptor, self._world)
