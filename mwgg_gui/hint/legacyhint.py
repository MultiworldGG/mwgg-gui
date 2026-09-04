from __future__ import annotations
__all__ = ("HintTooltipLabel",
           "FixedMDDropdownMenu",
           "MarkupDropdown",
           "HintLog",
           "HintLabel",
           "HintLayout",
           "RefToolTip",
           "status_names",
           "status_colors",
           "status_sort_weights",
           "status_icons",
           "mwggstatus_names",
           "mwggstatus_colors",
           "mwggstatus_icons",
           "mwggstatus_sort_weights",
           "mwgg_flags",
           "open_toggle_dropdown",
           "remove_between_brackets",
           )

from NetUtils import HintStatus, MWGGUIHintStatus, get_item_classification_label

from kivy.properties import BooleanProperty, ColorProperty
from kivy.app import App
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.utils import get_color_from_hex
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.recycleview import MDRecycleView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.menu.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.tooltip import MDTooltip, MDTooltipPlain
from kivy.core.text.markup import MarkupLabel
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard


from mwgg_gui.overrides import HoverLabel
from mwgg_gui.components.columns import (
    ColumnSorter, ColumnSortMixin, ColumnFilter, ColumnFilterMixin,
    ColumnFilterItemClassification, ColumnFilterMulti, ExtraColumn,
    get_extra_columns, register_extra_column as _register_extra_column,
)
from mwgg_gui.hint.hint_visibility import is_hidden, resolve_ui_hint_bucket, row_visible, with_hidden

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
status_icons: typing.Dict[HintStatus, str] = {
    HintStatus.HINT_NO_PRIORITY: "information",
    HintStatus.HINT_PRIORITY: "exclamation-thick",
    HintStatus.HINT_AVOID: "alert",
}

# Dict order is the display order: BK Mode outranks Goal outranks Shop.
mwggstatus_names: typing.Dict[MWGGUIHintStatus, str] = {
    MWGGUIHintStatus.HINT_BK_MODE: "BK Mode",
    MWGGUIHintStatus.HINT_GOAL: "Goal",
    MWGGUIHintStatus.HINT_SHOP: "Shop",
}
mwggstatus_colors: typing.Dict[MWGGUIHintStatus, str] = {
    MWGGUIHintStatus.HINT_BK_MODE: "trap_item_color",
    MWGGUIHintStatus.HINT_GOAL: "progression_item_color",
    MWGGUIHintStatus.HINT_SHOP: "regular_item_color",
}
mwggstatus_icons: typing.Dict[MWGGUIHintStatus, str] = {
    MWGGUIHintStatus.HINT_BK_MODE: "food",
    MWGGUIHintStatus.HINT_GOAL: "flag-checkered",
    MWGGUIHintStatus.HINT_SHOP: "shopping",
}
mwggstatus_sort_weights: dict[MWGGUIHintStatus, int] = {
    MWGGUIHintStatus.HINT_BK_MODE: 0,
    MWGGUIHintStatus.HINT_GOAL: 1,
    MWGGUIHintStatus.HINT_SHOP: 2,
    MWGGUIHintStatus.HINT_UNSPECIFIED: 3,
}
NO_FLAGS = "None"


def mwgg_flags(status: MWGGUIHintStatus) -> list[MWGGUIHintStatus]:
    """Flags set in ``status``, in display order."""
    return [flag for flag in mwggstatus_names if status & flag]


class RefToolTip(MDTooltipPlain):
    ref_color: ColorProperty

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ref_color = self.theme_cls.surfaceContainerLowestColor

class HintTooltipLabel(HoverLabel, MDTooltip):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(height=self.set_height)
        self.app = App.get_running_app()

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


class FixedMDDropdownMenu(MDDropdownMenu):
    """MDDropdownMenu that stays inside the window.

    KivyMD 2.0.0 picks the growth direction while the menu still has its
    100px placeholder width and only then widens it to 240dp, so a caller
    near the right edge overflows; it also treats "no room either way" as
    one side. Growth is chosen per axis from the real size, centering on
    the caller when neither side fits.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.width <= 100:
            self.width = dp(240)
        self._initial_width = self.width

    def check_ver_growth(self) -> None:
        margin = self.border_margin
        bad_down = self.target_height > self._start_coords[1] - margin
        bad_up = self.target_height > Window.height - self._start_coords[1] - margin
        if bad_down and bad_up:
            self.ver_growth = None
        elif bad_down:
            self.ver_growth = "up"
        else:
            self.ver_growth = "down"

    def check_hor_growth(self) -> None:
        margin = self.border_margin
        bad_right = self.width > Window.width - self._start_coords[0] - margin
        bad_left = self.width > self._start_coords[0] - margin
        if bad_right and bad_left:
            self.hor_growth = None
        elif bad_right:
            self.hor_growth = "left"
        else:
            self.hor_growth = "right"

    def get_target_pos(self) -> tuple[float, float]:
        x, y = self._start_coords
        if self.ver_growth == "up":
            y += self.height
        elif self.ver_growth is None:
            y += self.height / 2
        if self.hor_growth == "left":
            x -= self.width
        elif self.hor_growth is None:
            x -= self.width / 2
        self._tar_x, self._tar_y = x, y
        return x, y


class MarkupDropdown(FixedMDDropdownMenu):
    """Upstream kvui name kept for world clients; text items render markup
    through the theme's MDDropdownTextItem override."""


CHECKED_ICON = "checkbox-marked-outline"
UNCHECKED_ICON = "checkbox-blank-outline"


def open_toggle_dropdown(caller, items: list[dict],
                         after_toggle: typing.Callable[[bool], None] | None = None,
                         after_dropdown_closed: typing.Callable[[], None] | None = None
                         ) -> FixedMDDropdownMenu | None:
    """Open a menu of check-style toggles built from ColumnFilter.build_menu_items
    entries. The menu stays open across toggles so several can be flipped."""
    if not items:
        if after_dropdown_closed:
            after_dropdown_closed()
        return None
    menu = FixedMDDropdownMenu(caller=caller)

    def entry(item: dict) -> dict:
        return {
            "text": item["text"],
            "leading_icon": CHECKED_ICON if item["active"] else UNCHECKED_ICON,
            "on_release": lambda *_, item=item: toggle(item),
        }

    def toggle(item: dict) -> None:
        item["active"] = not item["active"]
        item["on_toggle"](item["active"])
        menu.items = [entry(i) for i in items]
        if after_toggle:
            after_toggle(item["active"])

    menu.items = [entry(item) for item in items]
    if after_dropdown_closed:
        menu.bind(on_dismiss=lambda *_: after_dropdown_closed())
    menu.open()
    return menu


class HintLabel(RecycleDataViewBehavior, MDBoxLayout):
    """One hint row. The same class renders the sticky column header
    (``index`` None, ``log`` set) so a tracker viewclass with extra columns
    lines up with its rows."""
    selected = BooleanProperty(False)
    striped = BooleanProperty(False)
    row_disabled = BooleanProperty(False)
    theme_bg_color = "Custom"
    index: int | None = None
    log: HintLog | None = None
    dropdown: FixedMDDropdownMenu

    def __init__(self):
        super().__init__()
        self.receiving_text = ""
        self.item_text = ""
        self.finding_text = ""
        self.location_text = ""
        self.entrance_text = ""
        self.status_text = ""
        self.flags_text = ""
        self.visible_text = ""
        self.hint = {}
        self.flag_status = MWGGUIHintStatus.HINT_UNSPECIFIED
        self.dropdown = FixedMDDropdownMenu(caller=self.ids["status"], items=[{
            "text": status_names[status],
            "leading_icon": status_icons[status],
            "on_release": lambda *_, status=status: self.select_status(status),
        } for status in (HintStatus.HINT_NO_PRIORITY, HintStatus.HINT_PRIORITY, HintStatus.HINT_AVOID)])
        # World-contributed columns (e.g. the tracker's in-logic status) get one
        # cell each, appended after the kv-declared ones.
        self.extra_cells: dict[str, HintTooltipLabel] = {}
        for column in get_extra_columns():
            cell = HintTooltipLabel(sort_key=column.key, halign="center", valign="center",
                                    pos_hint={"center_y": 0.5})
            self.add_widget(cell)
            self.extra_cells[column.key] = cell

    def select_status(self, status: HintStatus):
        ctx = App.get_running_app().ctx
        ctx.update_hint(self.hint["location"], self.hint["finding_player"], status)
        self.dropdown.dismiss()

    def set_flag(self, flag: MWGGUIHintStatus, active: bool):
        self.flag_status = self.flag_status | flag if active else self.flag_status & ~flag
        self._send_status(self.flag_status)

    def _send_status(self, status: MWGGUIHintStatus) -> None:
        ctx = App.get_running_app().ctx
        ctx.update_mwgg_hints({f"{self.hint['finding_player']}_{self.hint['location']}": int(status)})

    def open_flags_dropdown(self):
        open_toggle_dropdown(self.ids["flags"], [{
            "text": mwggstatus_names[flag],
            "active": bool(self.flag_status & flag),
            "on_toggle": lambda active, flag=flag: self.set_flag(flag, active),
        } for flag in mwggstatus_names])

    def toggle_hidden(self):
        """Flip this hint's client-owned hidden flag; the SetReply re-renders the table."""
        self._send_status(MWGGUIHintStatus(with_hidden(self.flag_status, not is_hidden(self.flag_status))))

    def fit_height(self, *_args) -> None:
        """Size the sticky header to its cells' rendered text. The header is built
        before the table has its width, so texts wrap and the grow-only
        set_height pins a tall row; this shrinks it back once textures settle."""
        cells = [child for child in self.children if hasattr(child, "texture_size")]
        text_height = max((child.texture_size[1] for child in cells), default=0) + dp(8)
        self.height = max(self.minimum_height, text_height)

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.striped = data.get("striped", False)
        self.receiving_text = data["receiving"]["text"]
        self.item_text = data["item"]["text"]
        self.finding_text = data["finding"]["text"]
        self.location_text = data["location"]["text"]
        self.entrance_text = data["entrance"]["text"]
        self.status_text = data["status"]["text"]
        flags = data.get("flags") or {}
        self.flags_text = flags.get("text", "")
        self.flag_status = flags.get("status", MWGGUIHintStatus.HINT_UNSPECIFIED)
        self.visible_text = data.get("visible", {}).get("text", "")
        self.hint = data["status"]["hint"]
        self.row_disabled = index is not None and self.hint["status"] == HintStatus.HINT_FOUND
        for key, cell in self.extra_cells.items():
            cell.text = data[key]["text"]
            cell.disabled = self.row_disabled
        return super().refresh_view_attrs(rv, index, data)

    def _owns_hint(self) -> bool:
        return App.get_running_app().ctx.slot_concerns_self(self.hint["receiving_player"])

    def plain_text(self) -> str:
        tags = [self.status_text.lower()] + [mwggstatus_names[flag].lower() for flag in mwgg_flags(self.flag_status)]
        text = "".join((self.receiving_text, "'s ", self.item_text, " is at ", self.location_text, " in ",
                        self.finding_text, "'s World",
                        (" at " + self.entrance_text) if self.entrance_text != "Vanilla" else "",
                        ". (", ", ".join(tags), ")"))
        text = "".join(part for part in MarkupLabel(text).markup if not part.startswith("["))
        return text.replace("&bl;", "[").replace("&br;", "]").replace("&amp;", "&")

    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        if not self.collide_point(*touch.pos):
            return False
        if self.index is None:
            return self._on_header_touch(touch)
        found = self.hint["status"] == HintStatus.HINT_FOUND
        if self.ids["status"].collide_point(*touch.pos):
            if found:
                return True
            if self._owns_hint():
                self.dropdown.open()
                return True
            return False
        if self.ids["flags"].collide_point(*touch.pos):
            if found:
                return True
            if self._owns_hint():
                self.open_flags_dropdown()
                return True
            return False
        if self.ids["visible"].collide_point(*touch.pos):
            if found:
                return True
            self.toggle_hidden()
            return True
        if self.selected:
            self.parent.clear_selection()
            return True
        Clipboard.copy(self.plain_text())
        return self.parent.select_with_touch(self.index, touch)

    def _on_header_touch(self, touch) -> bool:
        """Left-click sorts by the column, right-click opens its filter."""
        if self.log is None:
            return False
        self.log.layout_manager.clear_selection()
        for child in self.children:
            if not child.collide_point(*touch.pos):
                continue
            key = getattr(child, "sort_key", None)
            if key is None:
                return False
            app = App.get_running_app()
            if getattr(touch, "button", None) == "right":
                return self.log.pop_filter_dropdown_for(key, self.log.rows, child,
                                                        after_toggle=lambda _: app.update_hints())
            if self.log.sort_by_key(key):
                app.update_hints()
                return True
            return False
        return False

    def apply_selection(self, rv, index, is_selected):
        if self.index is not None:
            self.selected = is_selected


remove_between_brackets = re.compile(r"\[.*?]")


def _flags_weight(row: dict) -> int:
    flags = mwgg_flags(row["flags"]["status"])
    return mwggstatus_sort_weights[flags[0] if flags else MWGGUIHintStatus.HINT_UNSPECIFIED]


class HintLog(MDRecycleView, ColumnSortMixin, ColumnFilterMixin):
    """Classic hint table.

    The column header is built from the row viewclass and handed to
    HintLayout to sit above the recycle view, so sorting and filtering stay
    reachable however far the log is scrolled. Found hints are filtered out
    until the Status filter re-enables them.
    """
    header = {
        "receiving": {"text": "[u]Receiving Player[/u]"},
        "item": {"text": "[u]Item[/u]", "flags": 0},
        "finding": {"text": "[u]Finding Player[/u]"},
        "location": {"text": "[u]Location[/u]"},
        "entrance": {"text": "[u]Entrance[/u]"},
        "status": {"text": "[u]Status[/u]",
                   "hint": {"receiving_player": -1, "location": -1, "finding_player": -1, "status": ""}},
        "flags": {"text": "[u]Flags[/u]", "names": [], "status": MWGGUIHintStatus.HINT_UNSPECIFIED},
        "visible": {"text": "[u]Visible[/u]"},
        "striped": True,
    }
    data: list[typing.Any]
    rows: list[dict]
    header_widget: HintLabel

    def __init__(self, parser):
        super().__init__()
        self.data = []
        self.parser = parser
        self.rows = []
        self.extra_columns = get_extra_columns()
        if self.extra_columns:
            self.header = {**self.header, **{
                column.key: {"text": f"[u]{column.header_text}[/u]"} for column in self.extra_columns
            }}
        self.header_widget = self._build_header()
        # Sorters apply in order, so the last one is the primary sort; extra
        # columns sort first so a world's column doesn't silently become primary.
        for column in self.extra_columns:
            self.column_sorters.append(column.sorter)
        for key in ["entrance", "receiving", "finding", "item", "location"]:
            self.column_sorters.append(ColumnSorter(
                key,
                lambda row, k=key: remove_between_brackets.sub("", row[k]["text"]).lower(),
            ))
        self.column_sorters.append(ColumnSorter("flags", _flags_weight))
        self.column_sorters.append(ColumnSorter(
            "status",
            lambda row: status_sort_weights[row["status"]["hint"]["status"]],
            True
        ))

        for key in ["entrance", "receiving", "finding", "item", "location", "status"]:
            def conv(row, k=key):
                return remove_between_brackets.sub("", row[k]["text"])
            if key == "item":
                filt = ColumnFilterItemClassification(key, conv, lambda row: row["item"]["flags"])
            else:
                filt = ColumnFilter(key, conv)
            if key == "status":
                filt.option_list.update(status_names.values())
            self.column_filters.append(filt)
        flags_filter = ColumnFilterMulti("flags", lambda row: row["flags"]["names"] or [NO_FLAGS])
        flags_filter.option_list.update(mwggstatus_names.values())
        flags_filter.option_list.add(NO_FLAGS)
        self.column_filters.append(flags_filter)
        for column in self.extra_columns:
            if column.filter is not None:
                self.column_filters.append(column.filter)

    @classmethod
    def register_extra_column(cls, column: ExtraColumn) -> None:
        """Register a world-contributed hint-table column (see columns.ExtraColumn).

        Must be called before a HintLog instance is built (e.g. during a
        world's UI-extras setup phase), since header/sorters/filters are
        fixed at construction time.
        """
        _register_extra_column(column)

    def _build_header(self) -> HintLabel:
        cls = self.viewclass
        if isinstance(cls, str):
            cls = Factory.get(cls)
        header = cls()
        header.log = self
        header.refresh_view_attrs(self, None, self.header)
        for cell in header.children:
            cell.bind(texture_size=header.fit_height)
        header.fit_height()
        return header

    def pop_filter_dropdown_for(self, key: str, data: list[typing.Any], caller,
                                after_dropdown_closed: typing.Callable[[], None] | None = None,
                                after_toggle: typing.Callable[[bool], None] | None = None) -> bool:
        filt = self.get_filter(key)
        if filt is None:
            return False
        open_toggle_dropdown(caller, filt.build_menu_items(data), after_toggle, after_dropdown_closed)
        return True

    def refresh_hints(self, hints, mwgg_hints: dict | None = None):
        if not hints:  # Fix the scrolling looking visually wrong in some edge cases
            self.scroll_y = 1.0
        app = App.get_running_app()
        if app is None:
            return  # App is shutting down, skip hint refresh
        ctx = app.ctx
        if mwgg_hints is None:
            mwgg_hints = ctx.stored_data.get(f"hints_{ctx.team}_{ctx.slot}_mwgg", {}) or {}
        show_all = bool(getattr(app, "show_all_hints", False))
        ui_hint_data = getattr(app, "ui_hint_data", None) or {}
        rows = []
        for hint in hints:
            if not hint.get("status"): # Allows connecting to old servers
                hint["status"] = HintStatus.HINT_FOUND if hint["found"] else HintStatus.HINT_UNSPECIFIED
            editable = hint["status"] != HintStatus.HINT_FOUND and ctx.slot_concerns_self(hint["receiving_player"])
            mwgg_status = MWGGUIHintStatus(mwgg_hints.get(f"{hint['finding_player']}_{hint['location']}") or 0)
            # The UIHint (app.ui_hint_data) is the shared source of found/hide;
            # fall back to the raw hint before the data package has built it.
            bucket = resolve_ui_hint_bucket(hint, ctx.slot_concerns_self)
            ui_hint = ui_hint_data.get(bucket, {}).get(hint["location"]) if bucket is not None else None
            if ui_hint is not None:
                found, hidden = bool(ui_hint.found), bool(ui_hint.hide)
            else:
                found, hidden = hint["status"] == HintStatus.HINT_FOUND or bool(hint["found"]), is_hidden(mwgg_status)
            if not row_visible(found, hidden, show_all):
                continue
            item_flags = hint["item_flags"]
            if hint.get("item_hidden"):
                item_text = f"Hidden ({get_item_classification_label(item_flags)})"
            else:
                item_text = self.parser.handle_node({
                    "type": "item_id",
                    "text": hint["item"],
                    "flags": item_flags,
                    "player": hint["receiving_player"],
                })
            status_text = self.parser.handle_node({"type": "color",
                                                   "color": status_colors.get(hint["status"], "red"),
                                                   "text": status_names.get(hint["status"], "Unknown")})
            flags = mwgg_flags(mwgg_status)
            flags_text = ", ".join(self.parser.handle_node({"type": "color",
                                                            "color": mwggstatus_colors[flag],
                                                            "text": mwggstatus_names[flag]})
                                   for flag in flags) or NO_FLAGS
            if editable:
                status_text = f"[u]{status_text}[/u]"
                flags_text = f"[u]{flags_text}[/u]"
            row = {
                "receiving": {"text": self.parser.handle_node({"type": "player_id", "text": hint["receiving_player"]})},
                "item": {"text": item_text, "flags": item_flags},
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
                "status": {"text": status_text, "hint": hint},
                "flags": {"text": flags_text, "names": [mwggstatus_names[flag] for flag in flags], "status": mwgg_status},
                "visible": {"text": ("Unhide" if hidden else "Hide") if hint["status"] == HintStatus.HINT_FOUND
                            else f"[u]{'Unhide' if hidden else 'Hide'}[/u]"},
            }
            for column in self.extra_columns:
                column.build_value(hint, row)
            rows.append(row)

        self.rows = rows
        data = self.filter_columns(rows)
        self.sort_columns(data)

        for i in range(0, len(data), 2):
            data[i]["striped"] = True
        self.data = data


class HintLayout(MDBoxLayout):
    orientation = "vertical"

    def add_widget(self, widget, *args, **kwargs):
        # The visibility toolbar and header sit above the recycle view so they never scroll away.
        if isinstance(widget, HintLog):
            super().add_widget(self._build_toolbar(widget))
            super().add_widget(widget.header_widget)
        return super().add_widget(widget, *args, **kwargs)

    @staticmethod
    def _build_toolbar(log: HintLog) -> MDBoxLayout:
        """Eye switch = app.show_all_hints: on shows every hint for this slot, off
        drops found and hidden ones (its setter re-renders the hint screen)."""
        app = App.get_running_app()
        # active is set after construction: passing it as a kwarg fires on_active
        # before the switch has built its ids.
        switch = MDSwitch(icon_inactive="eye-off", icon_active="eye")
        switch.active = bool(getattr(app, "show_all_hints", False))
        switch.bind(active=lambda _inst, active: setattr(app, "show_all_hints", active))
        return MDBoxLayout(switch, size_hint_y=None, height=dp(40), padding=[dp(8), dp(4)])

# Deferred: legacyhint.kv references SelectableRecycleBoxLayout by name, and
# recycleview imports HintTooltipLabel from this module at module scope, so
# this import must happen after HintTooltipLabel is defined above.
from mwgg_gui.legacy.recycleview import SelectableRecycleBoxLayout

with open(
    os.path.join(os.path.dirname(__file__), "legacyhint.kv"), encoding="utf-8"
) as kv_file:
    Builder.load_string(kv_file.read())
