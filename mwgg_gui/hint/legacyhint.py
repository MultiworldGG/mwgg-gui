from __future__ import annotations
__all__ = ("HintTooltipLabel",
           "MarkupDropdown",
           "HintLog",
           "HintLabel",
           "HintLayout",
           "RefToolTip",
           "status_names", 
           "status_colors", 
           "status_sort_weights",
           "status_icons", 
           "remove_between_brackets",
           )

from NetUtils import HintStatus, MWGGUIHintStatus, TEXT_COLORS

from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.recycleview import MDRecycleView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.menu.menu import MDDropdownMenu
from kivymd.uix.tooltip import MDTooltip, MDTooltipPlain
from kivymd.uix.label import MDLabel
from kivymd.uix.behaviors import HoverBehavior
from kivy.core.text.markup import MarkupLabel
from kivy.metrics import dp
from kivy.utils import escape_markup
from kivy.core.clipboard import Clipboard

from mwgg_gui.overrides import HoverLabel
from mwgg_gui.components.columns import *

import re
import os
import typing

status_names: typing.Dict[HintStatus, str] = {
    HintStatus.HINT_FOUND: "Found",
    HintStatus.HINT_UNSPECIFIED: "Unspecified",
    HintStatus.HINT_NO_PRIORITY: "No Priority",
    HintStatus.HINT_AVOID: "Avoid",
    HintStatus.HINT_PRIORITY: "Priority",
}
# Theme-mapped: MAIN hard-coded dark-palette color names (green/white/
# lightgray/salmon/gold); these resolve through the MarkupTagsTheme-managed
# TEXT_COLORS entries instead, matching the new hint screen's palette
# semantics so Light mode stays coherent.
status_colors: typing.Dict[HintStatus, str] = {
    HintStatus.HINT_FOUND: "location_color",
    HintStatus.HINT_UNSPECIFIED: "default_color",
    HintStatus.HINT_NO_PRIORITY: "regular_item_color",
    HintStatus.HINT_AVOID: "trap_item_color",
    HintStatus.HINT_PRIORITY: "progression_item_color",
}
status_sort_weights: dict[HintStatus, int] = {
    HintStatus.HINT_FOUND: 0,
    HintStatus.HINT_UNSPECIFIED: 1,
    HintStatus.HINT_NO_PRIORITY: 2,
    HintStatus.HINT_AVOID: 3,
    HintStatus.HINT_PRIORITY: 4,
}

class RefToolTip(MDTooltipPlain):
    pass

class HintTooltipLabel(HoverLabel, MDTooltip):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(height=self.set_height)

    def set_height(self, inst, val):
        w, h = self.texture_size
        if h == 100:
            return h
        h = h + dp(8)
        if self.parent:
            if self.parent.height < h:
                self.parent.height = h
        return h

    def create_tooltip(self, text, pos):
        if self._tooltip:
            # update
            self._tooltip.text = text
        else:
            self._tooltip = RefToolTip(text=text, pos_hint={})
            # Back-ref so the tracker's clear_stray_tooltips can tell a
            # live hover from an orphan (kivymd sets it for kv children).
            self._tooltip._tooltip = self
            self.display_tooltip()

    def on_ref_hover(self, ref):
        if self.mw_ref:
            self.create_tooltip(self.mw_ref, self.enter_point)
        return True

    def on_leave(self):
        self.remove_tooltip()
        self._tooltip = None

class MarkupDropdown(MDDropdownMenu):
    def on_items(self, instance, value: list) -> None:
        """
        The method sets the class that will be used to create the menu item.
        """

        items = []
        viewclass = "MDDropdownTextItem"

        for data in value:
            if "viewclass" not in data:
                if (
                    "leading_icon" not in data
                    and "trailing_icon" not in data
                    and "trailing_text" not in data
                ):
                    viewclass = "MDDropdownTextItem"
                elif (
                    "leading_icon" in data
                    and "trailing_icon" not in data
                    and "trailing_text" not in data
                ):
                    viewclass = "MDDropdownLeadingIconItem"
                elif (
                    "leading_icon" not in data
                    and "trailing_icon" in data
                    and "trailing_text" not in data
                ):
                    viewclass = "MDDropdownTrailingIconItem"
                elif (
                    "leading_icon" not in data
                    and "trailing_icon" in data
                    and "trailing_text" in data
                ):
                    viewclass = "MDDropdownTrailingIconTextItem"
                elif (
                    "leading_icon" in data
                    and "trailing_icon" in data
                    and "trailing_text" in data
                ):
                    viewclass = "MDDropdownLeadingTrailingIconTextItem"
                elif (
                    "leading_icon" in data
                    and "trailing_icon" in data
                    and "trailing_text" not in data
                ):
                    viewclass = "MDDropdownLeadingTrailingIconItem"
                elif (
                    "leading_icon" not in data
                    and "trailing_icon" not in data
                    and "trailing_text" in data
                ):
                    viewclass = "MDDropdownTrailingTextItem"
                elif (
                    "leading_icon" in data
                    and "trailing_icon" not in data
                    and "trailing_text" in data
                ):
                    viewclass = "MDDropdownLeadingIconTrailingTextItem"

                data["viewclass"] = viewclass

            items.append(data)

        self._items = items
        # Update items in view
        if hasattr(self, "menu"):
            self.menu.data = self._items

status_icons = {
    HintStatus.HINT_NO_PRIORITY: "information",
    HintStatus.HINT_PRIORITY: "exclamation-thick",
    HintStatus.HINT_AVOID: "alert"
}

class HintLabel(RecycleDataViewBehavior, MDBoxLayout):
    selected = BooleanProperty(False)
    striped = BooleanProperty(False)
    theme_bg_color = "Custom"
    index = None
    dropdown: MDDropdownMenu
    row_disabled = BooleanProperty(False)

    def __init__(self):
        super(HintLabel, self).__init__()
        self.receiving_text = ""
        self.item_text = ""
        self.finding_text = ""
        self.location_text = ""
        self.entrance_text = ""
        self.status_text = ""
        self.hint = {}
        self.row_disabled = False

        ctx = App.get_running_app().ctx
        menu_items = []

        for status in (HintStatus.HINT_NO_PRIORITY, HintStatus.HINT_PRIORITY, HintStatus.HINT_AVOID):
            name = status_names[status]
            menu_items.append({
                "text": name,
                "leading_icon": status_icons[status],
                "on_release": lambda x=status: select(self, x)
            })

        self.dropdown = MDDropdownMenu(caller=self.ids["status"], items=menu_items)

        def select(instance, data):
            ctx.update_hint(self.hint["location"],
                            self.hint["finding_player"],
                            data)

        self.dropdown.bind(on_touch_up=self.dropdown.dismiss)

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.striped = data.get("striped", False)
        self.receiving_text = data["receiving"]["text"]
        self.item_text = data["item"]["text"]
        self.finding_text = data["finding"]["text"]
        self.location_text = data["location"]["text"]
        self.entrance_text = data["entrance"]["text"]
        self.status_text = data["status"]["text"]
        self.hint = data["status"]["hint"]
        if self.status_text == "Found":
            self.row_disabled = True
        return super(HintLabel, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        """ Add selection on touch down """
        if super(HintLabel, self).on_touch_down(touch):
            return True
        if self.index:  # skip header
            if self.collide_point(*touch.pos):
                status_label = self.ids["status"]
                if status_label.collide_point(*touch.pos):
                    if self.hint["status"] == HintStatus.HINT_FOUND:
                        return True
                    ctx = App.get_running_app().ctx
                    if ctx.slot_concerns_self(self.hint["receiving_player"]):  # If this player owns this hint
                        # open a dropdown
                        self.dropdown.open()
                        return True
                elif self.selected:
                    self.parent.clear_selection()
                    return True
                else:
                    text = "".join((self.receiving_text, "\'s ", self.item_text, " is at ", self.location_text, " in ",
                                    self.finding_text, "\'s World", (" at " + self.entrance_text)
                                    if self.entrance_text != "Vanilla"
                                    else "", ". (", self.status_text.lower(), ")"))
                    temp = MarkupLabel(text).markup
                    text = "".join(part for part in temp if not part.startswith("["))
                    Clipboard.copy(escape_markup(text).replace("&amp;", "&").replace("&bl;", "[").replace("&br;", "]"))
                    return self.parent.select_with_touch(self.index, touch)
        else:
            parent = self.parent
            parent.clear_selection()
            parent: HintLog = parent.parent
            # find correct column
            for child in self.children:
                if child.collide_point(*touch.pos):
                    if parent.sort_by_key(child.sort_key):
                        App.get_running_app().update_hints()
                        return True
                    return False
        return False

    def apply_selection(self, rv, index, is_selected):
        """ Respond to the selection of items in the view. """
        if self.index:
            self.selected = is_selected

class HintLayout(MDBoxLayout):
    orientation = "vertical"

remove_between_brackets = re.compile(r"\[.*?]")

class HintLog(MDRecycleView, ColumnSortMixin):
    header = {
        "receiving": {"text": "[u]Receiving Player[/u]"},
        "item": {"text": "[u]Item[/u]"},
        "finding": {"text": "[u]Finding Player[/u]"},
        "location": {"text": "[u]Location[/u]"},
        "entrance": {"text": "[u]Entrance[/u]"},
        "status": {"text": "[u]Status[/u]",
                    "hint": {"receiving_player": -1, "location": -1, "finding_player": -1, "status": ""}},
        "striped": True,
    }
    data: list[typing.Any]

    def __init__(self, parser):
        super(HintLog, self).__init__()
        self.data = [self.header]
        self.parser = parser
        # Setup default sorters for each key in a sensible default order
        # The last in the list will end up being the 'primary' sort, as each sorter is applied in-order.
        # Custom clients should be able to modify these and add additional sorters
        for key in ["entrance", "receiving", "finding", "item", "location"]:
            self.column_sorters.append(ColumnSorter(
                key,
                lambda element, k=key: remove_between_brackets.sub("", element[k]["text"]).lower(),
            ))
        self.column_sorters.append(ColumnSorter(
            "status",
            lambda element: status_sort_weights[element["status"]["hint"]["status"]],
            True
        ))

    def refresh_hints(self, hints):
        if not hints:  # Fix the scrolling looking visually wrong in some edge cases
            self.scroll_y = 1.0
        data = []
        app = App.get_running_app()
        if app is None:
            return  # App is shutting down, skip hint refresh
        ctx = app.ctx
        for hint in hints:
            if not hint.get("status"): # Allows connecting to old servers
                hint["status"] = HintStatus.HINT_FOUND if hint["found"] else HintStatus.HINT_UNSPECIFIED
            hint_status_node = self.parser.handle_node({"type": "color",
                                                        "color": status_colors.get(hint["status"], "red"),
                                                        "text": status_names.get(hint["status"], "Unknown")})
            if hint["status"] != HintStatus.HINT_FOUND and ctx.slot_concerns_self(hint["receiving_player"]):
                hint_status_node = f"[u]{hint_status_node}[/u]"
            data.append({
                "receiving": {"text": self.parser.handle_node({"type": "player_id", "text": hint["receiving_player"]})},
                "item": {"text": self.parser.handle_node({
                    "type": "item_id",
                    "text": hint["item"],
                    "flags": hint["item_flags"],
                    "player": hint["receiving_player"],
                })},
                "finding": {"text": self.parser.handle_node({"type": "player_id", "text": hint["finding_player"]})},
                "location": {"text": self.parser.handle_node({
                    "type": "location_id",
                    "text": hint["location"],
                    "player": hint["finding_player"],
                }) if not hint.get("hidden") else "Hidden"},
                "entrance": {"text": self.parser.handle_node({"type": "color" if hint["entrance"] else "text",
                                                                "color": 'entrance_color', "text": hint["entrance"]
                                                                if hint["entrance"] else "Vanilla"})
                                if not hint.get("hidden") else "Hidden"},
                "status": {
                    "text": hint_status_node,
                    "hint": hint,
                },
            })

        self.sort_columns(data)

        for i in range(0, len(data), 2):
            data[i]["striped"] = True
        data.insert(0, self.header)
        self.data = data


with open(
    os.path.join(os.path.dirname(__file__), "legacyhint.kv"), encoding="utf-8"
) as kv_file:
    Builder.load_string(kv_file.read())