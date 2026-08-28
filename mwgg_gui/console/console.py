from __future__ import annotations
"""
CONSOLE SCREEN
ConsoleSliverAppbar - Left side has the players, with expansion for hints TODO: rename and move to components (profile/hintlist)
ConsoleLayout - Right contains the console
"""
__all__ = ("ConsoleScreen", "ConsoleSliverAppbar", "ConsoleLayout")
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card.card import MDRelativeLayout
from .textconsole import ConsoleView
from .tracker_view import TrackerRegionList

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.sliverappbar import MDSliverAppbar, MDSliverAppbarContent
from kivymd.uix.list import MDList
from kivymd.theming import ThemableBehavior

from mwgg_gui.overrides.expansionlist import *
from mwgg_gui.components.bottomappbar import BottomAppBar
from mwgg_gui.components.columns import ColumnSortMixin, ColumnFilterMixin
from mwgg_gui.components.mw_theme import AutoAdjustHeightBehavior

import asynckivy

Builder.load_string('''
<ConsoleLayout>:
    id: console_layout
    pos: 0,82

<ConsoleSliverAppbar>:
    pos_hint: {"x": 0, "top": 1}
    width: dp(260)
    size_hint_x: None
    adaptive_height: True
    hide_appbar: True
    deafened_icon: "headphones"
    tracker_mode: False
    current_view: "players"
    background_color: app.theme_cls.secondaryContainerColor
    MDSliverAppbarHeader:
        AsyncImage:
            source: app.logo_png
            pos_hint: {"top": 1}
            fit_mode: "cover"
    MDTopAppBar:
        type: "small"
        pos_hint: {"center_x": 0.5, "top": 1}
        padding: dp(4),0,dp(4),dp(4)
        MDTopAppBarLeadingButtonContainer:
            MDActionTopAppBarButton:
                icon: "refresh"
                on_release: root.refresh_current_view()
        MDTopAppBarTitle:
            id: app_bar_title
            text: ("Logic" if root.current_view == "players" else "Players") if root.tracker_mode else "Flags"
            halign: "center"
            font_style: "Body"
            role: "medium"
            on_touch_down: root.handle_title_touch(self, args[1])
        MDTopAppBarTrailingButtonContainer:
            MDActionTopAppBarButton:
                icon: "food"
                on_release: root.set_bk()
            MDActionTopAppBarButton:
                icon: root.deafened_icon
                on_release: root.set_deafen()
''')

class ConsoleLayout(AutoAdjustHeightBehavior, MDRelativeLayout):
    adjust_title_bar = True
    adjust_app_bar = True
    adjust_bottom_appbar = True
    adjust_custom = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_x = 1

class ConsoleSliverAppbar(MDSliverAppbar, ColumnSortMixin, ColumnFilterMixin):
    # This class is kvui.HintLog in the monorepo, and world code (the Universal
    # Tracker's on_kv_post patch) registers ColumnSorter/ColumnFilter instances
    # on it. The hint screen reads those registrations to build its chips.
    content: MDSliverAppbarContent
    app: MDApp
    deafened_icon: StringProperty
    tracker_mode: BooleanProperty
    current_view: StringProperty
    screen_manager: MDScreenManager
    players_screen: MDScreen
    logic_screen: MDScreen

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # The cooperative __init__ chain normally reaches the mixins; keep the
        # registration lists present even if a base class breaks the chain.
        if not hasattr(self, "column_sorters"):
            self.column_sorters = []
        if not hasattr(self, "column_filters"):
            self.column_filters = []
        self.app = MDApp.get_running_app()
        self.content = MDSliverAppbarContent(orientation="vertical")
        self.content.id = "content"
        self.add_widget(self.content)

        # Client-direct processes never build a launcher screen (see
        # app.py._create_screen's client-role guard), so fall back to the
        # MWGG_CLIENT_TYPE env var the launcher spawned this process with.
        launcher = getattr(self.app, "launcher_screen", None)
        if launcher is not None:
            self.tracker_mode = getattr(launcher, "client_type", "") == "universal_tracker"
        else:
            self.tracker_mode = getattr(self.app, "client_type_hint", "") == "universal_tracker"

        self.screen_manager = MDScreenManager(size_hint_y=None, height=dp(48))
        self.players_screen = MDScreen(name="players", size_hint_y=None, height=dp(48))
        self.logic_screen = MDScreen(name="logic", size_hint_y=None, height=dp(48))
        self.screen_manager.add_widget(self.players_screen)
        self.screen_manager.add_widget(self.logic_screen)
        self.screen_manager.bind(current_screen=self._on_current_screen)
        self.content.add_widget(self.screen_manager)

    def set_bk(self):
        self.app.ctx.ui.set_bk()

    def set_deafen(self):
        '''
        Trigger deafened toggle, and set the icon to the opposite of what it is currently
        Function call takes too long to set the icon "correctly", so we go backwards.
        '''
        preemptive_deafened = not self.app.ctx.ui.local_player_data.deafened
        self.deafened_icon = "headphones-off" if preemptive_deafened else "headphones"

        self.app.ctx.ui.set_deafen()

    def toggle_view(self):
        '''Swap between the Players (hint slots) and Logic (tracker locations) screens.

        Switching to the logic view triggers a refresh so it populates
        immediately instead of sitting empty until the refresh button is hit.
        '''
        if not self.tracker_mode:
            return
        self.current_view = "logic" if self.current_view == "players" else "players"
        self.screen_manager.current = self.current_view
        if self.current_view == "logic":
            self.refresh_current_view()

    def handle_title_touch(self, title_widget, touch):
        '''Make the appbar title click-to-toggle when in Universal Tracker mode.'''
        if not self.tracker_mode:
            return False
        if title_widget.collide_point(*touch.pos):
            self.toggle_view()
            return True
        return False

    def _on_current_screen(self, manager, screen):
        '''Resize the screen_manager to match whichever screen just became active.

        Both screens size to their MDList content (minimum_height-driven),
        so the sliver appbar's outer ScrollView handles overflow and the
        header still collapses on scroll.
        '''
        if screen is None:
            return
        self._sync_screen_height(screen)
        if not getattr(screen, "_height_bound", False):
            screen.bind(height=lambda inst, h: self._sync_screen_height(inst))
            screen._height_bound = True

    def _sync_screen_height(self, screen):
        if self.screen_manager.current_screen is not screen:
            return
        self.screen_manager.height = max(screen.height, dp(48))

    def refresh_current_view(self):
        '''Refresh button: hints for players view, tracker locations for logic view.

        For the logic view we go through the overlay's tracker_overlay_refresh
        hook (installed by worlds/tracker/wrap.py:start_overlay_ui_refresh) so
        the same full pipeline as the periodic tick runs -- updateTracker(),
        page labels, and the location list repaint. Falls back to a UI-only
        repaint if the overlay hasn't installed the hook yet.
        '''
        if self.current_view == "logic" and self.tracker_mode:
            refresh = getattr(self.app.ctx, "tracker_overlay_refresh", None)
            if callable(refresh):
                refresh()
            else:
                self.app.console_screen.update_tracker_locations()
        else:
            self.app.ctx.ui.update_hints()




class ConsoleScreen(MDScreen, ThemableBehavior):
    '''
    This is the main screen for the console.
    Left side has the players, with expansion for hints
    Right contains the console
    '''
    name = "console"
    app: MDApp
    consolegrid: MDBoxLayout
    important_appbar: MDSliverAppbar
    ui_console: ConsoleView
    bottom_appbar: BottomAppBar


    def __init__(self, **kwargs):
        self.app = MDApp.get_running_app()
        self.size_hint = (1,1)
        self.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        super().__init__(**kwargs)
        self.slots_mdlist = MDList(width=260)
        self.tracker_regions_mdlist = TrackerRegionList(width=260)

        self.bottom_appbar = BottomAppBar(screen_name="console")

        self.important_appbar = ConsoleSliverAppbar()

        Clock.schedule_once(lambda x: self.init_important())

    def on_enter(self, *args):
        """Arm the console hover tooltip whenever this screen is shown.
        getattr-guarded: the first on_enter fires at startup before the
        Clock-deferred init_important has created ui_console."""
        console = getattr(self, "ui_console", None)
        if console is not None:
            console.text_console.start_hover_tracking()

    def on_leave(self, *args):
        console = getattr(self, "ui_console", None)
        if console is not None:
            console.text_console.stop_hover_tracking()

    def update_slots_list(self):
        """Update the slots list when hints data becomes available"""
        asynckivy.start(self.set_slots_list())

    def update_tracker_locations(self):
        """Repopulate the tracker region list from the current ctx.tracker_core state."""
        self.tracker_regions_mdlist.populate_from_ctx(self.app.ctx)

    def init_important(self):
        self.consolegrid = ConsoleLayout(width=Window.width, height=Window.height-185)
        self.add_widget(self.consolegrid)
        self.add_widget(self.bottom_appbar)


        self.important_appbar.size_hint_x = 260/Window.width
        self.important_appbar.size_hint_y=1-(8/Window.height)

        self.ui_console = ConsoleView(pos_hint={"y": 0, "center_x": .5+(130/Window.width)},
                                      size_hint_x=1-(264/Window.width),
                                      size_hint_y=1-(8/Window.height))
        self.important_appbar.ids.scroll.scroll_wheel_distance = 40

        # Players screen holds the slot/hint expansion list, sized to its content.
        self.slots_mdlist.size_hint_y = None
        self.slots_mdlist.bind(minimum_height=self.slots_mdlist.setter("height"))
        players_screen = self.important_appbar.players_screen
        players_screen.add_widget(self.slots_mdlist)
        self.slots_mdlist.bind(height=lambda inst, h: setattr(players_screen, "height", max(h, dp(48))))

        # Logic screen mirrors the Players screen: sized by its MDList content;
        # each region panel's inner RecycleView virtualizes its location rows,
        # keeping the outer list cheap for games with many regions.
        self.tracker_regions_mdlist.size_hint_y = None
        self.tracker_regions_mdlist.bind(
            minimum_height=self.tracker_regions_mdlist.setter("height"))
        logic_screen = self.important_appbar.logic_screen
        logic_screen.add_widget(self.tracker_regions_mdlist)
        self.tracker_regions_mdlist.bind(
            height=lambda inst, h: setattr(logic_screen, "height", max(h, dp(48))))

        # Kick off the initial screen-height sync now that children are wired.
        self.important_appbar._on_current_screen(
            self.important_appbar.screen_manager,
            self.important_appbar.screen_manager.current_screen,
        )

        self.consolegrid.add_widget(self.important_appbar)
        self.consolegrid.add_widget(self.ui_console)

        # If tracker mode is active, seed the locations list now that ctx exists.
        if self.important_appbar.tracker_mode:
            Clock.schedule_once(lambda dt: self.update_tracker_locations(), 0.5)

        # on_enter fired at startup before this deferred build created
        # ui_console, so re-arm hover tracking if this screen is visible;
        # start_hover_tracking is idempotent for later on_enter/on_leave.
        if self.manager and self.manager.current == self.name:
            self.ui_console.text_console.start_hover_tracking()

    def _get_slot_priority(self, slot_data) -> tuple[bool, int]:
        """
        Calculate priority for sorting slots.
        Returns (has_hints, -priority_value) where:
        - has_hints: True if slot has any visible hints, False otherwise
        - priority_value: negative of highest elevation level (for proper sorting)
        Priority order: 5 (highest), 4, 6, 3, 2, 1, 0
        """
        visible_hints = [
            hint for hint in slot_data.hints.values()
            if not hint.hide or self.app.show_all_hints
        ]
        
        if not visible_hints:
            return (False, 0)  # No hints, goes to end
        
        priority_order = {5: 0, 4: 1, 6: 2, 3: 3, 2: 4, 1: 5, 0: 6}
        highest_priority = 6  # Default to lowest priority
        
        for hint in visible_hints:
            classification = hint.assigned_classification if hint.assigned_classification else hint.classification
            
            if hint.found == "Found":
                elevation = 0
            elif classification == "Progression - Required for Goal":
                elevation = 6
            elif classification == "Progression":
                elevation = 5
            elif classification == "Progression - Logically Relevant":
                elevation = 4
            elif classification == "Useful":
                elevation = 3
            elif classification == "Filler":
                elevation = 2
            elif classification == "Trap":
                elevation = 1
            else:
                elevation = 0
            
            if elevation in priority_order:
                if priority_order[elevation] < highest_priority:
                    highest_priority = priority_order[elevation]
        
        return (True, -highest_priority)  # Negative for proper sorting (lower is better)

    async def set_slots_list(self):
        self.slots_mdlist.clear_widgets()
        
        slots_to_add = [
            (slot_id, slot_data)
            for slot_id, slot_data in self.app.ctx.ui.ui_player_data.items()
            if slot_data.slot_name != "Archipelago"
        ]
        
        # Has-hints first, then by elevation priority.
        slots_to_add.sort(key=lambda x: self._get_slot_priority(x[1]), reverse=True)
        
        for slot_id, slot_data in slots_to_add:
            await asynckivy.sleep(0)
            slot = GameListPanel(item_name=slot_id, item_data=slot_data)
            self.slots_mdlist.add_widget(slot)
