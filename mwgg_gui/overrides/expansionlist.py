from __future__ import annotations

from kivymd.uix.behaviors.backgroundcolor_behavior import BackgroundColorBehavior
from kivymd.uix.label import MDLabel
__all__ = ['GameListPanel', 
           'GameListItem', 
           'GameListItemLongText', 
           'GameListItemShortText', 
           'GameTrailingPressedIconButton',
           'SlotListItemHeader',
           'SlotListItem',
           'HintListItemHeader',
           'HintListItem',
           'HintListItemLabel',
           'HintListDropdown',
           'IconBadge',
           'calculate_text_height',
           ]
from textwrap import wrap

from kivy.animation import Animation
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, DictProperty, ObjectProperty, NumericProperty, BooleanProperty, ColorProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.behaviors import RotateBehavior, CommonElevationBehavior
from kivymd.theming import ThemableBehavior
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.badge import MDBadge
from kivy.core.text import Label as LabelBase

from kivymd.uix.list import *
from kivymd.uix.expansionpanel import *

from kivymd.uix.tooltip import MDTooltip

from kivy.lang import Builder
import os
import re
from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.icon_definitions import md_icons
from typing import TYPE_CHECKING, Any, Callable, Tuple
from NetUtils import MWGGUIHintStatus, HintStatus

if TYPE_CHECKING:
    from CommonClient import CommonContext

from mwgg_gui.components.guidataclasses import UIPlayerData, UIHint, HintStatus

with open(os.path.join(os.path.dirname(__file__), "expansionlist.kv"), encoding="utf-8") as kv_file:
    Builder.load_string(kv_file.read())

def calculate_text_height(text: str, font_size: float, text_width: float) -> float:
    """Measure rendered text height via LabelBase with wrapping at text_width."""
    label = LabelBase(text=text, font_size=font_size, text_size=(text_width, None))
    label.refresh()
    return label.texture.size[1] if label.texture else font_size

class IconBadge(MDBadge):
    """Badge widget for displaying icons."""
    pass

class HintListItemHeader(MDBoxLayout, ButtonBehavior, ThemableBehavior):
    """Header row for a hint item."""
    hint_icon: StringProperty
    hint_text: StringProperty
    panel: ObjectProperty
    
    def __init__(self, hint_icon: str, hint_text: str, panel: "HintListPanel", **kwargs):
        self.hint_icon = hint_icon
        self.hint_text = hint_text
        self.panel = panel
        super().__init__(**kwargs)

class SlotListItemHeader(MDBoxLayout, CommonElevationBehavior):
    """Header showing a slot's name (with pronouns) and game."""
    slot_name: StringProperty
    game: StringProperty
    panel: ObjectProperty
    search: BooleanProperty
    waiting: BooleanProperty

    def __init__(self, item_data, panel, **kwargs):
        self.panel = panel
        self.item_data = item_data
        self.theme_shadow_color = "Custom"
        self.theme_elevation_level = "Custom"
        self.elevation_level = 0
        if self.item_data.pronouns:
            self.slot_name = self.item_data.slot_name + " (" + self.item_data.pronouns + ")"
        else:
            self.slot_name = self.item_data.slot_name
        self.game = self.item_data.game
        self.search = False
        self.waiting = False
        super().__init__(**kwargs)
        Clock.schedule_once(lambda x: self.calculate_height())

    def calculate_height(self):
        """Compute header height from real texture sizes (no reactive bindings)."""
        # Available width for text 100 default kivy width
        # total width - children(avatar - trailing icon - spacing) - padding - spacing
        children_width = 0
        for child in self.children:
            if child.__class__.__name__ == "MDBoxLayout":
                children_width += child.padding[0]
                children_width += child.padding[2]
                children_width += self.spacing
            else:
                children_width += 0 if child.width == 100 else child.width
                children_width += self.spacing

        if self.panel.width == 100:
            text_width = 256 - dp(40) - dp(24) - children_width - self.padding[0] - self.padding[2]
        else:
            text_width = self.width - children_width - self.padding[0] - self.padding[2]

        name_height = calculate_text_height(self.slot_name, self.ids.slot_item_name.font_size, text_width)
        game_height = calculate_text_height(self.game, self.ids.slot_item_game.font_size, text_width)
        self.height = dp(36) + name_height + game_height

    def set_elevation_and_shadow(self):
        self.elevation_level = 0
        self.shadow_color = self.theme_cls.shadowColor
        self.search = False
        self.waiting = False
        for child in self.panel.panel_content.children:
            if isinstance(child, SlotListItem):
                if child.elevation_level > self.elevation_level:
                    self.elevation_level = child.elevation_level
                    self.shadow_color = child.shadow_color if child.shadow_color != self.theme_cls.shadowColor else self.theme_cls.shadowColor
                if child.my_item:
                    self.waiting = True
                else:
                    self.search = True

class GameListItemHeader(MDBoxLayout, ButtonBehavior, ThemableBehavior):
    """Header row for a game entry in the game list."""
    game_module: StringProperty
    game_data: DictProperty
    panel: ObjectProperty
    on_game_select: ObjectProperty = None

    def __init__(self, game_module, game_data, panel, on_game_select=None, **kwargs):
        self.game_module = game_module
        self.game_data = game_data
        self.panel = panel
        self.on_game_select = on_game_select
        self.style = "Tonal"
        super().__init__(**kwargs)

    def on_release(self, *args):
        """Handle press event for game selection"""
        if self.on_game_select:
            self.on_game_select(self.game_module)

    def list_tooltip(self, item_list: list[str]) -> dict[str, str]:
        """Wrap items into a shortened 'label' and a full 'tooltip' text."""
        full_list = ", ".join(item_list).rstrip(", ")
        wrapped_list = wrap(full_list, width=17, break_on_hyphens=False, max_lines=3)
        item_dict = {
            "label": "\n".join(wrapped_list).rstrip("\n"),
            "tooltip": "\n".join(wrap(full_list, width=40, break_on_hyphens=False)).rstrip("\n")
        }
        return item_dict

class MWBaseListItem(MDBoxLayout, CommonElevationBehavior):
    """Base list item showing a hint's entrance, location, item, and goal."""
    entrance_texture: Tuple[NumericProperty, NumericProperty]
    slot_icon_entrance: ObjectProperty
    slot_text_entrance: ObjectProperty
    slot_icon_location: ObjectProperty
    slot_text_location: ObjectProperty
    slot_icon_item: ObjectProperty
    slot_text_item: ObjectProperty
    slot_icon_goal: ObjectProperty
    item_name: StringProperty
    location_name: StringProperty
    entrance_name: StringProperty
    game_status: StringProperty
    my_item: BooleanProperty
    for_bk_mode: BooleanProperty
    for_goal: BooleanProperty
    from_shop: BooleanProperty
    classification: StringProperty
    assigned_level: StringProperty
    found: StringProperty
    item_badge_text: StringProperty
    location_badge_text: StringProperty

    def __init__(self, hint_data: UIHint, game_status: str, shadow_colors: dict, **kwargs):
        from NetUtils import HintStatus, MWGGUIHintStatus
        self.hint_data = hint_data
        self.game_status = game_status
        self.entrance_name = self.hint_data.entrance if self.hint_data.entrance else "Vanilla"
        self.location_name = self.hint_data.location
        self.item_name = self.hint_data.item
        self.classification = self.hint_data.classification
        self.found = self.hint_data.found
        self.status = self.hint_data.hint_status
        self.mwgg_status = self.hint_data.mwgg_hint_status
        self.my_item = self.hint_data.my_item

        super().__init__(**kwargs)

        self.item_badge_text = ""
        self.location_badge_text = ""
        if self.mwgg_status & MWGGUIHintStatus.HINT_BK_MODE:
            self.item_badge_text += md_icons["food"] + " "
        if self.mwgg_status & MWGGUIHintStatus.HINT_GOAL:
            self.item_badge_text += md_icons["flag_checkered"] + " "
        if self.mwgg_status & MWGGUIHintStatus.HINT_SHOP:
            self.location_badge_text += md_icons["shop"]

    def populate_slot_item(self):
        pass

    def set_prio_behavior(self, item_colors: dict[str, list[str]]):
        if self.hint_data.assigned_classification:
            self.classification = self.hint_data.assigned_classification
        if self.classification == "Trap":
            self.elevation_level = 1
            self.shadow_color = item_colors["trap"]
        if self.classification == "Filler":
            self.elevation_level = 2
            self.shadow_color = item_colors["regular"]
        if self.classification == "Useful":
            self.elevation_level = 3
            self.shadow_color = item_colors["useful"]
        if self.classification == "Progression - Logically Relevant":
            self.elevation_level = 4
            self.shadow_color = item_colors["logically_required"]
        if self.classification == "Progression":
            self.elevation_level = 5
            self.shadow_color = item_colors["progression"]
        if self.classification == "Progression - Required for Goal":
            self.elevation_level = 6
            self.shadow_color = item_colors["goal"]
        if self.found == "Found":
            self.elevation_level = 0

    def list_tooltip(self, item_list: list[str]) -> dict[str, str]:
        """Wrap items into a shortened 'label' and a full 'tooltip' text."""
        full_list = ", ".join(item_list).rstrip(", ")
        wrapped_list = wrap(full_list, width=17, break_on_hyphens=False, max_lines=3)
        item_dict = {
            "label": "\n".join(wrapped_list).rstrip("\n"),
            "tooltip": "\n".join(wrap(full_list, width=40, break_on_hyphens=False)).rstrip("\n")
        }
        return item_dict

class SlotListItem(MWBaseListItem):
    """
    Widget for displaying individual slot items in the slot list.
    """
    def __init__(self, hint_data: UIHint, game_status: str, shadow_colors: dict, **kwargs):
        super().__init__(hint_data, game_status, shadow_colors, **kwargs)
        self.slot_icon_location = self.ids.slot_icon_location
        self.slot_text_location = self.ids.slot_text_location
        self.slot_icon_item = self.ids.slot_icon_item
        self.slot_text_item = self.ids.slot_text_item
        self.slot_icon_goal = self.ids.slot_icon_goal

        if self.item_badge_text != "":
            self.slot_icon_item.add_widget(IconBadge(text=self.item_badge_text.rstrip()))
        if self.location_badge_text != "":
            self.slot_icon_location.add_widget(IconBadge(text=self.location_badge_text.rstrip()))

        Clock.schedule_once(lambda x: self.populate_slot_item())
        Clock.schedule_once(lambda x: self.set_prio_behavior(shadow_colors), .5)

        self.height = self.estimate_height()

    def populate_slot_item(self):
        """Populate entrance, location, item, and goal widgets."""
        if "Vanilla" not in self.entrance_name:
            # Server encodes unknown entrances as "Unknown location (ID:X)";
            # show just the identifier (e.g. "B1").
            entrance_text = self.entrance_name
            match = re.match(r"Unknown location \(ID:(.+)\)", entrance_text)
            if match:
                self.entrance_name = match.group(1).strip()

            self.slot_text_entrance = (MDListItemSupportingText(text=self.entrance_name, do_wrap=True))
            self.slot_icon_entrance = (MDListItemLeadingIcon(icon="door-open", pos_hint={"center_y": 0.55}))
            self.slot_item_middle_container = (MDBoxLayout(orientation="horizontal", spacing=dp(4), size_hint_y=.5, pos_hint={"center_y": 0.5}))
            self.slot_item_middle_container.add_widget(self.slot_icon_entrance)
            self.slot_item_middle_container.add_widget(self.slot_text_entrance)
            self.add_widget(self.slot_item_middle_container, 1)
        self.slot_text_location.text = self.location_name
        self.slot_text_item.text = self.item_name
        self.slot_icon_goal.icon = "flag_checkered" if self.game_status == "GOAL" else "blank"

    def estimate_height(self):
        """Compute item height from real texture sizes (no reactive bindings)."""
        # Available width for text (total width - icon - padding - spacing)
        text_width = 256 - dp(40) - dp(24) - dp(16)
        
        # Base height: padding + spacing
        nheight = dp(36) + (dp(4) * len(self.children))
        
        # Calculate entrance height if present
        if self.entrance_name != "Vanilla" and self.entrance_name:
            slot_text_entrance = getattr(self, 'slot_text_entrance', None)
            entrance_font_size = slot_text_entrance.font_size if slot_text_entrance else self.slot_text_location.font_size
            nheight += calculate_text_height(self.entrance_name, entrance_font_size, text_width)
        
        # Calculate location and item heights
        nheight += calculate_text_height(self.location_name, self.slot_text_location.font_size, text_width)
        nheight += calculate_text_height(self.item_name, self.slot_text_item.font_size, text_width)
        
        return nheight

class HintListItem(RecycleDataViewBehavior, BoxLayout, BackgroundColorBehavior, CommonElevationBehavior):
    """
    Widget for displaying individual hint items in the hint list.
    """
    theme_bg_color = StringProperty("Custom")
    theme_shadow_color = StringProperty("Custom")
    theme_elevation_level = StringProperty("Custom")
    md_bg_color = ColorProperty([0,0,0,1])
    player_name = StringProperty("")
    player_avatar = StringProperty("")
    hint_icon_status = StringProperty("")
    hint_status_text = StringProperty("")
    hint_data = ObjectProperty(None)
    item_name = StringProperty("")
    location_name = StringProperty("")
    entrance_name = StringProperty("")
    game_status = StringProperty("")
    my_item = BooleanProperty(False)
    bk_check = BooleanProperty(False)
    goal_check = BooleanProperty(False)
    shop_check = BooleanProperty(False)
    bk_icon = StringProperty("blank")
    goal_icon = StringProperty("blank")
    shop_icon = StringProperty("blank")
    # for_bk_mode = BooleanProperty(False)
    # for_goal = BooleanProperty(False)
    # from_shop = BooleanProperty(False)
    classification = StringProperty("")
    assigned_level = StringProperty("")
    found = StringProperty("")
    item_badge_text = StringProperty("")
    location_badge_text = StringProperty("")
    dropdown: MDDropdownMenu
    editable = BooleanProperty(False)
    shadow_color = ColorProperty([0,0,0,0])
    elevation_level = NumericProperty(0)
    hide = BooleanProperty(False)
    panel: ObjectProperty
    elevation_levels = {0: dp(0), 1: dp(1), 2: dp(1), 3: dp(1), 4: dp(2), 5: dp(2), 6: dp(2)}
    index = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dropdown = None
        self._remove_hint_event = None
        # self.fbind('bk_check', self.for_bk_mode)
        # self.fbind('goal_check', self.for_goal)
        # self.fbind('shop_check', self.from_shop)
        # self.fbind('bk_icon', lambda icon: icon = "food" if self.for_bk_mode else "blank")
        # self.fbind('goal_icon', lambda icon: icon = "flag_checkered" if self.for_goal else "blank")
        # self.fbind('shop_icon', lambda icon: icon = "shop" if self.from_shop else "blank")

    def refresh_view_attrs(self, rv, index, data):
        """Update view when RecycleView data changes"""
        self.index = index
        
        # Directly set properties from data dict (like HintLabel pattern)
        self.hint_data = data.get("hint_data", None)
        self.hide = self.hint_data.hide
        self.bk_check = self.hint_data.for_bk_mode
        self.goal_check = self.hint_data.for_goal
        self.shop_check = self.hint_data.from_shop
        self.bk_icon = "food" if self.hint_data.for_bk_mode else "blank"
        self.goal_icon = "flag_checkered" if self.hint_data.for_goal else "blank"
        self.shop_icon = "shop" if self.hint_data.from_shop else "blank"
        
        # Normalize entrance name if needed
        if "Vanilla" not in self.entrance_name and self.entrance_name:
            match = re.match(r"Unknown location \(ID:(.+)\)", self.entrance_name)
            if match:
                self.entrance_name = match.group(1).strip()
        
        # Setup dropdown if editable
        if self.editable and self.hint_data:
            self._ensure_dropdown()
        elif self.dropdown:
            self.dropdown.dismiss()
            self.dropdown = None
        

        super().refresh_view_attrs(rv, index, data)
        
        setattr(self.ids.slot_mwgg_status_checkbox_bk, 'active', self.bk_check)    
        setattr(self.ids.slot_mwgg_status_checkbox_goal, 'active', self.goal_check)
        setattr(self.ids.slot_mwgg_status_checkbox_shop, 'active', self.shop_check)
        setattr(self.ids.slot_mwgg_status_icon_bk, 'icon', self.bk_icon)
        setattr(self.ids.slot_mwgg_status_icon_goal, 'icon', self.goal_icon)
        setattr(self.ids.slot_mwgg_status_icon_shop, 'icon', self.shop_icon)
        setattr(self.ids.hide_checkbox, 'active', self.hide)

    
    def _ensure_dropdown(self):
        """Ensure dropdown is created if needed"""
        if self.dropdown or not hasattr(self, 'ids') or 'hint_item_status_button' not in self.ids:
            return
        
        from mwgg_gui.hint.hintscreen import status_names, status_icons
        from NetUtils import HintStatus
        
        def on_select_status(status: HintStatus):
            if self.hint_data:
                self.hint_data.set_status(hint_status=status)
        
        self.dropdown = HintListDropdown(
            caller=self.ids.hint_item_status_button,
            status_names=status_names,
            status_icons=status_icons,
            dropdown_callback=on_select_status
        )


    def store_checkbox_state(self, value):
        """Store the checkbox state"""
        rv = MDApp.get_running_app().root.ids.RelativeLayout
        rv.data[self.index]["hide"] = self.ids.hide_checkbox.active
        self.checkbox_state = self.ids.hide_checkbox.active

    def open_dropdown(self):
        """Open the status dropdown menu"""
        if self.dropdown:
            self.dropdown.open()
    
    
    @staticmethod
    def on_hide(hint_instance, value):
        """Handle hide checkbox change"""
        if hint_instance.hint_data:
            HintListItem._toggle_mwgg_flag_and_update(hint_instance, 0b1000, value)
            # return if it's already hidden (no removal animation needed)
            try:
                weak_class_name = hint_instance.__class__.__name__
                if weak_class_name == "HintListItem_Hidden":
                    return
                # Unschedule any existing pending removal animation
                if hint_instance._remove_hint_event:
                    Clock.unschedule(hint_instance._remove_hint_event)
                # Schedule new removal and store the event
                hint_instance._remove_hint_event = Clock.schedule_once(
                    lambda x: hint_instance.remove_hint(hint_instance, value), 1.5
                )
            except Exception as e:
                # weakref was probably deleted, pass silently
                pass

    @staticmethod
    def remove_hint(hint_instance, value):
        try:
            # Clear the stored event since it's now executing
            hint_instance._remove_hint_event = None
            if not hint_instance.hint_data.hide:
                return
            parent = getattr(hint_instance, 'parent', None)
            if parent and parent.recycleview and hint_instance.index is not None:
                animation = Animation(x=-(hint_instance.width+dp(24)), duration=0.5)
                animation.start(hint_instance)
                animation.on_complete = hint_instance.on_complete
        except Exception as e:
            # weakref was probably deleted, pass silently
            pass

    @staticmethod
    def on_complete(hint_instance):
        try:
            parent = getattr(hint_instance, 'parent', None)
            if parent and parent.recycleview and hint_instance.index is not None:
                    parent.recycleview.data.pop(hint_instance.index)
                    parent.recycleview.refresh_from_data()
            hint_instance._remove_hint_event = None
        except Exception as e:
            # weakref was probably deleted, pass silently
            pass


    @staticmethod
    def hide_hint(hint_instance, value):
        hint_instance.hint_data.hide = value

    @staticmethod
    def _toggle_mwgg_flag_and_update(hint_instance, flag: int, value: bool):
        """Helper method to toggle MWGG flag and update hints"""
        from kivymd.app import MDApp
        hint_instance.hint_data.toggle_mwgg_flag(flag, value)
        app = MDApp.get_running_app()
        if hasattr(app, 'update_mwgg_hints'):
            app.update_mwgg_hints()

    @staticmethod
    def set_bkmode(hint_instance, value):
        """Handle BK mode button activation"""
        HintListItem._toggle_mwgg_flag_and_update(hint_instance, 0b100, value)
    
    @staticmethod
    def set_goal(hint_instance, value):
        """Handle goal button activation"""
        HintListItem._toggle_mwgg_flag_and_update(hint_instance, 0b010, value)
    
    @staticmethod
    def set_shop(hint_instance, value):
        """Handle shop button activation"""
        HintListItem._toggle_mwgg_flag_and_update(hint_instance, 0b001, value)

class HintListDropdown(MDDropdownMenu):
    def __init__(self, *args, status_names: dict[HintStatus, str], status_icons: dict[HintStatus, str], 
                 dropdown_callback: Callable[[HintStatus], None], **kwargs):
        # Create items before calling super().__init__
        items = []
        for status in (HintStatus.HINT_NO_PRIORITY, HintStatus.HINT_PRIORITY, HintStatus.HINT_AVOID):
            name = status_names[status]
            items.append({
                "text": name,
                "leading_icon": status_icons[status],
                "on_release": lambda x=status: self._on_item_release(dropdown_callback, x)
            })
        
        super().__init__(*args, items=items, **kwargs)
    
    def _on_item_release(self, callback: Callable[[HintStatus], None], status: HintStatus):
        """Handle item release and dismiss dropdown"""
        callback(status)
        self.dismiss()

class ListItemTooltip(MDTooltip):
    """Tooltip behavior base for list items."""
    pass

class HintListItemLabel(ListItemTooltip, MDLabel):
    """Label with a tooltip carrying the full (possibly truncated) text."""
    tooltip_text = StringProperty("")
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tooltip_text = self.text

class GameListItemLongText(ListItemTooltip, MDListItemSupportingText):
    """Supporting text with a tooltip carrying the full text."""
    text = StringProperty("")
    tooltip_text = StringProperty("")

    def __init__(self, text, tooltip_text, **kwargs):
        self.text = text
        self.tooltip_text = tooltip_text
        super().__init__(**kwargs)

class GameListItemShortText(MDListItemSupportingText):
    """Supporting text without a tooltip, for text that fits."""
    text = StringProperty("")
    
    def __init__(self, text, **kwargs):
        self.text = text
        super().__init__(**kwargs)

class GameListItem(MDListItem, CommonElevationBehavior):
    """
    One metadata row (genre, theme, ...) in a game panel; long text gets a
    tooltip with the full content.
    """
    text = StringProperty("")
    icon = StringProperty("")
    tooltip_text = StringProperty("")
    
    def __init__(self, text="", icon="blank", tooltip_text="", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.icon = icon
        self.tooltip_text = tooltip_text
        self.width = 256
        self.pos_hint = {"center_y": 0.5}

        Clock.schedule_once(lambda x: self.remove_extra_container())
        if "..." in self.text:
            text_widget = GameListItemLongText(text, tooltip_text)
        else:
            text_widget = GameListItemShortText(text)
        self.add_widget(text_widget)

    def remove_extra_container(self):
        """Remove the unused trailing container from the list item."""
        try:
            self.remove_widget(self.ids.trailing_container)
        except:
            pass

class GameListPanel(MDExpansionPanel):
    """
    Expansion panel for the game list or hint list: shows slot items when
    item_data is UIPlayerData (hints), game metadata otherwise.
    """
    item_name: StringProperty
    item_data: Any
    icon = StringProperty("game-controller")
    leading_avatar: MDListItemLeadingAvatar
    panel_header: MDExpansionPanelHeader
    panel_content: MDExpansionPanelContent
    panel_header_layout: ObjectProperty
    on_game_select: ObjectProperty = None
    app: MDApp
    
    def __init__(self, item_name, item_data, on_game_select=None, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.item_name = item_name
        self.item_data = item_data
        self.on_game_select = on_game_select
        self.width = 256
        self.pos_hint = {"center_y": 0.5}
        if isinstance(self.item_data, UIPlayerData):
            Clock.schedule_once(lambda x: self.populate_slot_item(ctx=self.app.ctx))
            Clock.schedule_once(lambda x: self.set_self_height(), 1)
        else:
            Clock.schedule_once(lambda x: self.populate_game_item())

    def set_self_height(self):
        self.panel_content.height = self.panel_content.minimum_height

    def populate_slot_item(self, ctx: "CommonContext"):
        """Build the avatar header and one SlotListItem per visible hint."""
        self.panel_header = self.ids.panel_header
        self.panel_content = self.ids.panel_content
        self.panel_header_layout = SlotListItemHeader(item_data=self.item_data, panel=self)
        self.leading_avatar = self.panel_header_layout.ids.leading_avatar
        self.panel_header.add_widget(self.panel_header_layout)
        self.leading_avatar.source = "" if not self.item_data['avatar'] else self.item_data['avatar']
        i = 1 if self.app.theme_cls.theme_style == "Dark" else 0
        item_colors = {
            "trap": self.app.theme_mw.markup_tags_theme.trap_item_color[i],
            "regular": self.app.theme_mw.markup_tags_theme.regular_item_color[i],
            "useful": self.app.theme_mw.markup_tags_theme.useful_item_color[i],
            "progression_deprioritized": self.app.theme_mw.markup_tags_theme.progression_deprioritized_item_color[i],
            "progression": self.app.theme_mw.markup_tags_theme.progression_item_color[i],
            "progression_goal": self.app.theme_mw.markup_tags_theme.progression_goal_item_color[i],
            }
        for hint in self.item_data.hints.values():
            if self.app.show_all_hints or not (hint.hide or hint.found):
                item_widget = SlotListItem(hint_data=hint, game_status=self.item_data.game_status, shadow_colors=item_colors)
                self.panel_content.add_widget(item_widget)

        Clock.schedule_once(lambda x: self.panel_header_layout.set_elevation_and_shadow(), .5)
        if self.panel_header_layout.search:
            self.panel_header_layout.ids.slot_item_container.add_widget(BaseListItemIcon(icon="toy-brick-search", theme_font_size="Custom", font_size=dp(14), pos_hint={"center_y": 0.5}),1)
        if self.panel_header_layout.waiting:
            self.panel_header_layout.ids.slot_item_container.add_widget(BaseListItemIcon(icon="timer-sand", theme_font_size="Custom", font_size=dp(14), pos_hint={"center_y": 0.5}),1)
        if self.item_data.bk_mode:
            self.panel_header_layout.ids.slot_item_container.add_widget(BaseListItemIcon(icon="food", theme_font_size="Custom", font_size=dp(14), pos_hint={"center_y": 0.5}),1)
        if self.item_data.deafened:
            self.panel_header_layout.ids.slot_item_container.add_widget(BaseListItemIcon(icon="headphones-off", theme_font_size="Custom", font_size=dp(14), pos_hint={"center_y": 0.5}),1)
        if self.item_data.game_status == "GOAL":
            self.panel_header_layout.ids.game_item_container.add_widget(BaseListItemIcon(icon="flag_checkered", theme_font_size="Custom", font_size=dp(14), pos_hint={"center_y": 0.5}),1)

    def populate_game_item(self):
        """Build the header and metadata rows (genres, themes, ratings, ...)."""
        self.panel_header = self.ids.panel_header
        self.panel_content = self.ids.panel_content
        self.panel_header_layout = GameListItemHeader(
            game_module=self.item_name, 
            game_data=self.item_data, 
            panel=self,
            on_game_select=self.on_game_select
        )
        self.leading_avatar = self.panel_header_layout.ids.leading_avatar
        self.panel_header.add_widget(self.panel_header_layout)
        self.leading_avatar.source = self.item_data['cover_url']
        for item in self.item_data:
            if item == "genres" and self.item_data['genres']:
                list_tooltip = self.list_tooltip(self.item_data['genres'])
                self.panel_content.add_widget(GameListItem(text=list_tooltip['label'], icon="dice-multiple", tooltip_text=list_tooltip['tooltip']))
            elif item == "themes" and self.item_data['themes']:
                list_tooltip = self.list_tooltip(self.item_data['themes'])
                self.panel_content.add_widget(GameListItem(text=list_tooltip['label'], icon="sword", tooltip_text=list_tooltip['tooltip']))
            # elif item == "keywords" and self.item_data['keywords']:
            #     list_tooltip = self.list_tooltip(self.item_data['keywords'])
            #     self.panel_content.add_widget(GameListItem(text=list_tooltip['label'], icon="tag-outline", tooltip_text=list_tooltip['tooltip']))
            elif item == "player_perspectives" and self.item_data['player_perspectives']:
                list_tooltip = self.list_tooltip(self.item_data['player_perspectives'])
                self.panel_content.add_widget(GameListItem(text=list_tooltip['label'], icon="eye-outline", tooltip_text=list_tooltip['tooltip']))
            elif item == "rating" and self.item_data['rating']:
                list_tooltip = self.list_tooltip(self.item_data['rating'])
                self.panel_content.add_widget(GameListItem(text=list_tooltip['label'], icon="alert-box-outline", tooltip_text=list_tooltip['tooltip']))
            elif item == "release_date" and self.item_data['release_date']:
                self.panel_content.add_widget(GameListItem(text=str(self.item_data['release_date']), icon="calendar-month", tooltip_text=str(self.item_data['release_date'])))
                
    def list_tooltip(self, item_list: list[str]) -> dict[str, str]:
        """Wrap items into a shortened 'label' and a full 'tooltip' text."""
        full_list = ", ".join(item_list).rstrip(", ")
        wrapped_list = wrap(full_list, width=18, break_on_hyphens=False, max_lines=3)
        item_dict = {
            "label": "\n".join(wrapped_list).rstrip("\n"),
            "tooltip": "\n".join(wrap(full_list, width=40, break_on_hyphens=False)).rstrip("\n")
        }
        return item_dict

    def toggle_expansion(self, instance):
        """Open/close with padding animation and chevron update."""
        current_padding = self.padding
        new_padding = [dp(4), dp(12), dp(4), dp(12)] if not self.is_open else [dp(8),dp(4),dp(8),dp(4)]
        if current_padding != new_padding:
            Animation(
                padding=new_padding,
                d=0.2,
            ).start(self)
        self.open() if not self.is_open else self.close()
        self.set_chevron_up(instance) if self.is_open else self.set_chevron_down(instance)

class GameTrailingPressedIconButton(
    ButtonBehavior, RotateBehavior, MDListItemTrailingIcon
):
    """Pressable, rotatable trailing icon button for list items."""
    ...