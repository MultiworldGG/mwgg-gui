from __future__ import annotations
"""
TRACKER VIEW

TrackerLocationRecycleView - MDRecycleView showing one expandable row per
    region (Universal Tracker mode). Each row's expansion state lives in the
    RecycleView data dict so it survives widget recycling.
TrackerRegionPanel - RecycleView viewclass that renders a region header and,
    when expanded, the list of locations under that region.
"""
__all__ = ("TrackerLocationRecycleView", "TrackerRegionPanel")

import logging

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
from kivy.uix.recycleboxlayout import RecycleBoxLayout  # noqa: F401 -- registers for kv
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

logger = logging.getLogger("Client")

_HEADER_HEIGHT = dp(48)
_LOCATION_ROW_HEIGHT = dp(36)

Builder.load_string('''
<TrackerLocationRecycleView>:
    # size_hint = (1, 1) defaults so the RV fills its parent (logic_screen,
    # which is sized to the sliver appbar viewport). Inner RecycleBoxLayout
    # grows past that and the RV recycles widgets as the user scrolls.
    viewclass: "TrackerRegionPanel"
    bar_width: dp(6)
    RecycleBoxLayout:
        id: rbl
        default_size: None, dp(48)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: "vertical"
        spacing: dp(2)
        padding: dp(4), dp(4), dp(4), dp(4)

<TrackerRegionPanel>:
    orientation: "vertical"
    size_hint_y: None
    height: root.row_height
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.surfaceContainerColor
    radius: [dp(8), dp(8), dp(8), dp(8)]
    MDBoxLayout:
        id: header
        orientation: "horizontal"
        size_hint_y: None
        height: dp(48)
        padding: dp(8), dp(4), dp(8), dp(4)
        spacing: dp(4)
        MDIcon:
            id: chevron
            icon: "chevron-down" if root.expanded else "chevron-right"
            size_hint_x: None
            width: dp(24)
            pos_hint: {"center_y": 0.5}
        MDLabel:
            id: region_label
            text: root.region_name
            theme_text_color: "Custom"
            text_color: app.theme_cls.onSurfaceColor
            font_style: "Body"
            role: "medium"
            shorten: True
            shorten_from: "right"
            pos_hint: {"center_y": 0.5}
        MDLabel:
            id: count_label
            text: root.count_label_text
            size_hint_x: None
            width: dp(48)
            theme_text_color: "Custom"
            text_color: app.theme_cls.onSurfaceVariantColor
            halign: "right"
            font_style: "Body"
            role: "small"
            pos_hint: {"center_y": 0.5}
    MDBoxLayout:
        id: content
        orientation: "vertical"
        size_hint_y: None
        height: 0
        padding: dp(28), 0, dp(8), dp(4)
        spacing: dp(1)
''')


class TrackerLocationRecycleView(RecycleView):
    """RecycleView that lists a player's missing locations grouped by region."""

    app: MDApp

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.data = []

    def populate_from_ctx(self, ctx) -> None:
        """Rebuild the data list from the running TrackerGameContext.

        Pulls regions + locations from ctx.tracker_core.multiworld and filters
        each region's locations against ctx.tracker_core.missing_locations.
        Regions with no remaining missing locations are skipped.
        """
        tracker_core = getattr(ctx, "tracker_core", None)
        if tracker_core is None:
            logger.debug("populate_from_ctx: no tracker_core on ctx")
            self.data = []
            self.refresh_from_data()
            return

        multiworld = getattr(tracker_core, "multiworld", None)
        player_id = getattr(tracker_core, "player_id", None)
        if multiworld is None or player_id is None:
            logger.debug("populate_from_ctx: tracker_core not yet initialized")
            self.data = []
            self.refresh_from_data()
            return

        missing: set[int] = set(getattr(tracker_core, "missing_locations", set()))
        in_logic_addrs: set[int] = set(getattr(tracker_core, "locations_available", []) or [])

        # Preserve expansion state across reloads by region name.
        prev_expanded = {row["region_name"]: row["expanded"] for row in self.data}

        new_data: list[dict] = []
        try:
            regions = multiworld.get_regions(player_id)
        except Exception as exc:
            logger.exception(f"populate_from_ctx: get_regions failed: {exc}")
            self.data = []
            self.refresh_from_data()
            return

        for region in regions:
            locations = []
            for loc in getattr(region, "locations", []) or []:
                if loc.address is None:
                    continue
                if loc.address not in missing:
                    continue
                locations.append({
                    "name": loc.name,
                    "in_logic": loc.address in in_logic_addrs,
                })
            if not locations:
                continue
            locations.sort(key=lambda l: (not l["in_logic"], l["name"]))
            expanded = prev_expanded.get(region.name, False)
            new_data.append({
                "region_name": region.name,
                "locations": locations,
                "expanded": expanded,
                "row_height": _row_height(expanded, len(locations)),
            })

        new_data.sort(key=lambda r: r["region_name"])
        self.data = new_data
        self.refresh_from_data()


def _row_height(expanded: bool, location_count: int) -> float:
    if not expanded:
        return _HEADER_HEIGHT
    return _HEADER_HEIGHT + (_LOCATION_ROW_HEIGHT * location_count) + dp(8)


class TrackerRegionPanel(RecycleDataViewBehavior, MDBoxLayout):
    """One expandable region row inside the TrackerLocationRecycleView."""

    region_name = StringProperty("")
    locations = ListProperty([])
    expanded = BooleanProperty(False)
    row_height = NumericProperty(_HEADER_HEIGHT)
    count_label_text = StringProperty("")
    index = None
    _content_box: ObjectProperty = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_header, 0)

    def _bind_header(self, _dt):
        header = self.ids.get("header") if hasattr(self, "ids") else None
        if header is not None and not getattr(header, "_tracker_bound", False):
            header.bind(on_touch_down=self._on_header_touch)
            header._tracker_bound = True

    def _on_header_touch(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self._toggle()
            return True
        return False

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.region_name = data.get("region_name", "")
        self.locations = data.get("locations", [])
        self.expanded = data.get("expanded", False)
        self.row_height = data.get("row_height", _HEADER_HEIGHT)
        self.count_label_text = str(len(self.locations))
        Clock.schedule_once(lambda dt: self._render_content(), 0)
        return super().refresh_view_attrs(rv, index, data)

    def _render_content(self):
        content = self.ids.get("content") if hasattr(self, "ids") else None
        if content is None:
            return
        content.clear_widgets()
        if not self.expanded:
            content.height = 0
            return
        app = MDApp.get_running_app()
        in_logic_color = app.theme_cls.onSurfaceColor
        out_logic_color = app.theme_cls.onSurfaceVariantColor
        for loc in self.locations:
            label = MDLabel(
                text=loc["name"],
                theme_text_color="Custom",
                text_color=in_logic_color if loc["in_logic"] else out_logic_color,
                font_style="Body",
                role="small",
                size_hint_y=None,
                height=_LOCATION_ROW_HEIGHT,
                shorten=True,
                shorten_from="right",
            )
            content.add_widget(label)
        content.height = _LOCATION_ROW_HEIGHT * len(self.locations) + dp(4)

    def _toggle(self):
        rv = self.parent.recycleview if self.parent and hasattr(self.parent, "recycleview") else None
        if rv is None or self.index is None:
            return
        new_expanded = not self.expanded
        new_height = _row_height(new_expanded, len(self.locations))
        rv.data[self.index]["expanded"] = new_expanded
        rv.data[self.index]["row_height"] = new_height
        rv.refresh_from_data()
