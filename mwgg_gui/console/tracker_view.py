from __future__ import annotations
"""
TRACKER VIEW

TrackerRegionList - MDList containing one TrackerRegionPanel per top-level
    branch region (Universal Tracker mode). Sized by its content via
    minimum_height like the Players-side slots_mdlist.
TrackerRegionPanel - MDExpansionPanel subclass; header is a region name +
    count, expanded content is an inner RecycleView listing missing
    locations as uniform-height labels.
TrackerLocationItem - RecycleView viewclass for one location row, colored
    by its in-logic state.
"""
__all__ = ("TrackerRegionList", "TrackerRegionPanel", "TrackerLocationItem")

import logging

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.recycleboxlayout import RecycleBoxLayout  # noqa: F401 -- registered for kv
from kivy.uix.recycleview import RecycleView  # noqa: F401 -- registered for kv
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.app import MDApp
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList

from mwgg_gui.overrides.expansionlist import GameListPanel

logger = logging.getLogger("Client")

_HEADER_HEIGHT = dp(48)
_LOCATION_ITEM_HEIGHT = dp(36)
_CONTENT_SPACING = dp(1)
_CONTENT_PADDING_V = dp(4)


Builder.load_string('''
<-TrackerRegionPanel>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: dp(4), dp(2), dp(4), dp(2)
    md_bg_color: app.theme_cls.surfaceContainerColor
    theme_bg_color: "Custom"
    radius: [dp(8), dp(8), dp(8), dp(8)]
    MDExpansionPanelHeader:
        id: panel_header
        size_hint_y: None
        height: root.panel_header_height
        padding: dp(8), 0, dp(8), 0
        spacing: dp(4)
        MDIcon:
            id: chevron
            icon: "chevron-down" if root.is_open else "chevron-right"
            size_hint_x: None
            width: dp(24)
            pos_hint: {"center_y": 0.5}
        MDLabel:
            text: root.region_name
            theme_text_color: "Custom"
            text_color: app.theme_cls.onSurfaceColor
            font_style: "Body"
            role: "medium"
            shorten: True
            shorten_from: "right"
            pos_hint: {"center_y": 0.5}
        MDLabel:
            text: root.count_label_text
            size_hint_x: None
            width: dp(48)
            theme_text_color: "Custom"
            text_color: app.theme_cls.onSurfaceVariantColor
            halign: "right"
            font_style: "Body"
            role: "small"
            pos_hint: {"center_y": 0.5}
    MDExpansionPanelContent:
        id: panel_content
        orientation: "vertical"
        size_hint_y: None
        height: root.content_height
        # Left/right gutters give the user a clickable strip outside the
        # inner RecycleView so dragging there scrolls the outer MDList
        # instead of the inner RV (which otherwise captures all touches).
        padding: dp(16), 0, dp(16), 0
        RecycleView:
            id: rv
            viewclass: "TrackerLocationItem"
            bar_width: dp(10)
            # When the location list fits inside the panel viewport there's
            # nothing to scroll; disable scrolling and overscroll bounce
            # so a drag falls through to the outer MDList instead.
            do_scroll_y: rl.minimum_height > self.height
            always_overscroll: False
            RecycleBoxLayout:
                id: rl
                orientation: "vertical"
                default_size: None, root.item_height
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                padding: dp(12), dp(4), 0, dp(4)
                spacing: 1

<TrackerLocationItem>:
    size_hint_y: None
    height: dp(36)
    theme_text_color: "Custom"
    font_style: "Body"
    role: "small"
    shorten: True
    shorten_from: "right"
    valign: "center"
''')


# Maps the overlay_features CATEGORY_* strings to MarkupTagsTheme attrs.
_CATEGORY_TO_THEME_ATTR = {
    "default": "tracker_in_logic",
    "hinted": "tracker_hinted",
    "excluded": "tracker_excluded",
    "glitched": "tracker_glitched",
    "hinted_glitched": "tracker_hinted_glitched",
    "excluded_glitched": "tracker_excluded_glitched",
}


def _make_category_color_lookup(app):
    """Return a memoised category-name → hex-string resolver pulling from
    ``app.theme_mw.markup_tags_theme`` so the logic view tracks user-tuned
    mw_theme colors (and theme-style switches) instead of the tracker
    page's hardcoded Tracker.kv hexes.
    """
    cache: dict[str, str] = {}
    theme_mw = getattr(app, "theme_mw", None)
    markup = getattr(theme_mw, "markup_tags_theme", None) if theme_mw else None
    theme_style = getattr(theme_mw, "theme_style", "Dark") if theme_mw else "Dark"
    idx = 1 if theme_style == "Dark" else 0

    def lookup(category: str) -> str:
        if category in cache:
            return cache[category]
        attr_name = _CATEGORY_TO_THEME_ATTR.get(category)
        hex_str = ""
        if markup is not None and attr_name:
            pair = getattr(markup, attr_name, None)
            if isinstance(pair, (list, tuple)) and len(pair) > idx:
                hex_str = pair[idx] or ""
        cache[category] = hex_str
        return hex_str

    return lookup


class TrackerLocationItem(RecycleDataViewBehavior, MDLabel):
    """One location row inside an expanded TrackerRegionPanel."""

    def refresh_view_attrs(self, rv, index, data):
        self.text = data.get("name", "")
        app = MDApp.get_running_app()
        fallback = app.theme_cls.onSurfaceColor
        self.text_color = get_color_from_hex(data.get("color_hex", "")) if data.get("color_hex", "") else fallback
        return super().refresh_view_attrs(rv, index, data)


class TrackerRegionPanel(GameListPanel):
    """Expansion panel for one top-level branch's missing locations.

    Mirrors HintListPanel: a fixed-height header, plus an
    MDExpansionPanelContent whose target height is computed from the
    actual item count, not a guess.
    """

    region_name = StringProperty("")
    count_label_text = StringProperty("")
    panel_header_height = NumericProperty(_HEADER_HEIGHT)
    content_height = NumericProperty(0)
    item_height = NumericProperty(_LOCATION_ITEM_HEIGHT)

    def __init__(self, region_name: str, locations: list[dict], **kwargs):
        self._tracker_locations = locations
        super().__init__(item_name=region_name, item_data=locations, **kwargs)
        self.size_hint_x = 1
        self.width = 260
        self.pos_hint = {}
        self.region_name = region_name
        self.count_label_text = str(len(locations))
        self._populated = False
        Clock.schedule_once(lambda dt: self._populate(), 0)

    def populate_game_item(self):
        return

    def populate_slot_item(self, ctx=None):
        return

    def set_self_height(self):
        return

    def _populate(self):
        if self._populated:
            return
        self._populated = True
        rv = self.ids.rv
        rv.data = list(self._tracker_locations)
        rv.refresh_from_data()
        self._sync_content_height()

    def _calculate_content_height(self) -> float:
        count = len(self._tracker_locations)
        if count == 0:
            return dp(8)
        item_block = (
            count * (self.item_height + _CONTENT_SPACING)
            + (_CONTENT_PADDING_V * 2)
        )
        host = self.parent
        viewport = host.height if host else Window.height
        max_height = max(viewport - self.panel_header_height, dp(96))
        return min(item_block, max_height)

    def _sync_content_height(self, *_args):
        calculated = self._calculate_content_height()
        self.content_height = calculated
        self._original_content_height = calculated
        if self._content is not None and not self.is_open:
            self._content.height = 0

    def _set_content_height(self, *args):
        self._sync_content_height()

    def _update_original_content_height(self, widget):
        self._sync_content_height()

    def toggle_expansion(self, instance=None):
        if self.is_open:
            self.close()
        else:
            self._sync_content_height()
            self.open()

    def on_touch_down(self, touch):
        header = self.ids.get("panel_header") if hasattr(self, "ids") else None
        if header is not None and header.collide_point(*touch.pos):
            self.toggle_expansion()
            return True
        return super().on_touch_down(touch)


class TrackerRegionList(MDList):
    """MDList of TrackerRegionPanel widgets, sized by its content."""

    app: MDApp

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.size_hint_y = None
        self._expansion_state: dict[str, bool] = {}

    def populate_from_ctx(self, ctx) -> None:
        """Rebuild the region panels from the running TrackerGameContext."""
        tracker_core = getattr(ctx, "tracker_core", None)
        if tracker_core is None:
            logger.debug("populate_from_ctx: no tracker_core on ctx")
            self.clear_widgets()
            return

        multiworld = getattr(tracker_core, "multiworld", None)
        player_id = getattr(tracker_core, "player_id", None)
        if multiworld is None or player_id is None:
            logger.debug("populate_from_ctx: tracker_core not yet initialized")
            self.clear_widgets()
            return

        try:
            from worlds.tracker.overlay_features import (
                group_reachable_by_top_level_branch,
            )
            branches = group_reachable_by_top_level_branch(tracker_core)
        except Exception as exc:
            logger.exception(
                f"populate_from_ctx: group_reachable_by_top_level_branch failed: {exc}"
            )
            self.clear_widgets()
            return

        for child in list(self.children):
            if isinstance(child, TrackerRegionPanel):
                self._expansion_state[child.region_name] = bool(child.is_open)

        color_for = _make_category_color_lookup(self.app)

        self.clear_widgets()
        for branch_name, locations in branches:
            location_dicts = [
                {"name": name, "category": category,
                 "color_hex": color_for(category)}
                for name, category in locations
            ]
            panel = TrackerRegionPanel(
                region_name=branch_name, locations=location_dicts
            )
            self.add_widget(panel)
            if self._expansion_state.get(branch_name, False):
                Clock.schedule_once(
                    lambda dt, p=panel: p.toggle_expansion(), 0.05
                )
