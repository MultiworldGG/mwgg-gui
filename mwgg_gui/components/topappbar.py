from __future__ import annotations
"""
TopAppBar class - creates the top app bar that will be added to
the top of the screen.  Additionally creates helper functions to bind
to the mouse and window events to display the appropriate icon

TODO: I don't think Launcher needs the topappbar at all.

"""
from kivymd.app import MDApp
from kivymd.uix.appbar import MDTopAppBar, MDTopAppBarTitle, MDActionTopAppBarButton
from kivymd.uix.button import MDButtonText, MDButton
from kivy.lang import Builder
from kivy.uix.anchorlayout import AnchorLayout
from kivy.properties import (ObjectProperty,
                             ColorProperty,
                             NumericProperty,
                             BooleanProperty)
from .progress_overlay import ProgressOverlay
from .profile import show_profile
from kivy.clock import Clock
from time import time, strftime, gmtime, localtime
from kivy.metrics import dp
import logging
import re
import asyncio
import urllib.parse
import asynckivy
from Utils import persistent_store, persistent_load, format_SI_prefix
from mwgg_gui.constants import ROLE_LAUNCHER


logger = logging.getLogger("MultiWorld")

__all__ = ("TopAppBarLayout", "TopAppBar")

Builder.load_string('''
<Timer>:

<ServerLabel>:

<EnergyLinkLabel>:

<ClockLabel>:

<TopAppBarLayout>:

<TopAppBar>:
    MDTopAppBarLeadingButtonContainer:
        MDActionTopAppBarButton:
            icon: "menu"
            id: menu_button
            on_release: app.open_top_appbar_menu(self)
    EnergyLinkLabel:
        size_hint_x: .10
        id: energy_link_label
        text: ""
    ServerLabel:
        size_hint_x: .6
        id: server_info_label
        text: "Not Connected"
    ClockLabel:
        id: clock_label
        size_hint_x: .15
    MDTopAppBarTrailingButtonContainer:
        id: trailing_container
''')

class EnergyLinkLabel(MDTopAppBarTitle):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ctx = MDApp.get_running_app().ctx
        self.theme_font_style = "Custom"
        self.font_style = "Monospace"
        self.role = "large"
        self.text = "Energy Link: Standby"
        if hasattr(self.ctx, 'current_energy_link_value'):
            self.ctx.bind(current_energy_link_value=self.set_new_energy_link_value)

    def set_new_energy_link_value(self, instance, value):
        self.text = f"EL: {format_SI_prefix(value)}J"

class ClockLabel(MDTopAppBarTitle):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ctx = MDApp.get_running_app().ctx
        self.theme_font_style = "Custom"
        self.font_style = "Monospace"
        self.role = "large"
        self.text = strftime("%H:%M", localtime())
        asyncio.create_task(self.update_clock(), name="Clock")

    async def update_clock(self):
        while not self.ctx.exit_event.is_set():
            self.text = strftime("%H:%M", localtime())
            await asyncio.sleep(60)


class Timer(MDTopAppBarTitle):
    start_time = NumericProperty(0)
    elapsed_time = NumericProperty(0)
    is_running = BooleanProperty(False)
    slot_info = ObjectProperty(None)
    has_been_started = BooleanProperty(False)  # Track if timer has ever been started
    ctx = ObjectProperty(None)
    _update_event = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_font_style = "Custom"
        self.font_style = "Monospace"
        self.role = "large"
        self.theme_text_color = "Custom"
        self.text_color = self.theme_cls.onSurfaceVariantColor
        self.text = "00:00:00"
        self.bind(elapsed_time=self.on_elapsed_time)
        self.bind(is_running=self.on_is_running)
        
    def on_ui_built(self):
        self.ctx = MDApp.get_running_app().ctx
        self.slot_info = self.ctx.slot_info

    def on_is_running(self, instance, value):
        """Called when is_running property changes"""
        if value:
            instance.text_color = self.theme_cls.primaryColor
        else:
            instance.text_color = self.theme_cls.onSurfaceVariantColor
    
    def start_running_timer(self):
        """Start the timer (initial start or resume from pause)"""
        if self.ctx.timer:
            if self.ctx.timer > time():
                self.start()

    def start(self):
        """Start the timer (initial start or resume from pause)"""
        if not self.is_running:
            if self.ctx.timer:
                if self.ctx.timer < 1:
                    self.start_time = time()
                    self.ctx.timer = self.start_time
                else:
                    self.start_time = self.ctx.timer
            else:
                self.start_time = time()
                self.ctx.timer = self.start_time
            self.has_been_started = True
            self.is_running = True
            Clock.schedule_interval(self._update_timer_wrapper, 0.1)

    def stop(self):
        """Pause the timer (doesn't reset)"""
        if self.is_running:
            self.is_running = False
            Clock.unschedule(self._update_timer_wrapper)

    def reset(self):
        """Reset the timer to 00:00:00 and set new start time"""
        self.stop()
        self.text = "00:00:00"
        self.has_been_started = False
        self.start_time = 0

    def _update_timer_wrapper(self, dt):
        """Non-blocking wrapper for timer updates"""
        try:
            self.update_timer()
        except Exception as e:
            logger.exception(e)
    
    def update_timer(self):
        """Update the elapsed time and check for goal condition"""
       
        if self.is_running:
            self.start_time = self.ctx.timer
            self.elapsed_time = time() - self.start_time
            if self.slot_info and self.slot_info.get('game_status') == "GOAL":
                self.stop()
                return


    def on_elapsed_time(self, instance, value):
        """Called when elapsed_time property changes"""
        if value < 0:
            abs_value = abs(value)
            self.text = "-" + strftime("%H:%M:%S", gmtime(abs_value))
        else:
            if value > 86400:
                plural = "s" if value > 172800 else ""
                self.text = strftime(f"%d day{plural}, %H:%M:%S", gmtime(int(value)))
            else:
                self.text = strftime("%H:%M:%S", gmtime(int(value)))
    
    def on_parent(self, instance, parent):
        """Clean up scheduled events when widget is removed"""
        if parent is None and self._update_event:
            Clock.unschedule(self._update_event)
            self._update_event = None
 
class ServerLabel(MDTopAppBarTitle):
    """
    Label for the server and information
    """
    ctx: ObjectProperty
    initial_height: NumericProperty
    _connected: BooleanProperty(False)

    def __init__(self, **kwargs):
        self._connected = False
        super().__init__(**kwargs)
        self.theme_font_style = "Custom"
        self.font_style = "Monospace"
        self.role = "large"

    def on_text(self, instance, value):
        """Step the title role down when text grows taller than the first
        text this label held."""
        if not hasattr(self, 'initial_height'):
            self.initial_height = self.texture_size[1]
            return
        if self.texture_size[1] > self.initial_height and self.role == "large":
            self.role = "medium"
        elif self.texture_size[1] > self.initial_height and self.role == "medium":
            self.role = "small"

    def on_ui_built(self):
        self.ctx = MDApp.get_running_app().ctx
        self.slot_info = self.ctx.slot_info
        self._connected = True
        self.update_server_info()

    def update_server_info(self, ctx=None):
        """Update server info display - called directly from on_connect"""
        if not ctx:
            ctx = self.ctx
        if not ctx:
            return

        server_address = f"{urllib.parse.urlparse(ctx.server_address).hostname}:{urllib.parse.urlparse(ctx.server_address).port}"
        if ctx.slot is not None:
            name = ctx.player_names[ctx.slot]
            if hasattr(ctx.slot_info[ctx.slot], 'alias') and ctx.slot_info[ctx.slot].alias:
                name = ctx.slot_info[ctx.slot].alias
            self.text = f"{server_address} hosting {name} and friends"
        else:
            self.text = f"{server_address}"

    def on_disconnect(self):
        """Called when disconnected from server"""
        self._connected = False
        self.text = "Not Connected"

    def on_parent(self, instance, parent):
        """Clean up when widget is removed"""
        if parent is None:
            self._connected = False


    

class TopAppBar(MDTopAppBar):
    """
    Top app bar, kept transparent so the underlying progress overlay can
    show location-completion progress (driven by p_width).
    """
    
    timer: ObjectProperty
    server_info_label: ObjectProperty
    p_width: NumericProperty = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.server_info_label = self.ids.server_info_label
        self.energy_link_label = self.ids.energy_link_label
        self.theme_bg_color = "Custom"
        self.md_bg_color = self.theme_cls.transparentColor
        self.theme_shadow_color = "Custom"
        self.shadow_color = self.theme_cls.transparentColor
        # Role switch: the kv rule carries only the common chrome; the
        # role-specific pieces are constructed here, never pruned after.
        trailing = self.ids.trailing_container
        if self.app.role == ROLE_LAUNCHER:
            # The launcher process never connects (every launch spawns a
            # separate client process) -- no server text, no timer. The
            # trailing slots hold the Website/Discord shortcuts instead.
            self.server_info_label.text = ""
            self.timer = None
            self.timer_button = None
            for icon, component_name in (("web", "MultiworldGG Website"),
                                         ("discord", "Unofficial AP Discord")):
                button = MDActionTopAppBarButton(icon=icon)
                button.bind(on_release=lambda *_a, name=component_name: self._open_builtin(name))
                trailing.add_widget(button)
        else:
            self.timer = Timer(size_hint_x=.15)
            self.add_widget(self.timer)
            self.timer_button = MDActionTopAppBarButton(icon="timer-outline")
            self.timer_button.bind(on_release=lambda *_a: self.toggle_timer(),
                                   on_long_press=self.reset)
            trailing.add_widget(self.timer_button)
        profile_button = MDActionTopAppBarButton(icon="account-circle-outline")
        profile_button.bind(on_release=lambda *_a: self.open_profile())
        trailing.add_widget(profile_button)
        asyncio.create_task(self.update_progress_info(), name="ProgressBar")

    async def update_progress_info(self):
        """Update progress width and server info from the game session every 30s."""
        while not self.app.ctx.exit_event.is_set():
            if self.app.ctx and hasattr(self.app.ctx, 'total_locations') and self.app.ctx.total_locations:
                self.server_info_label.update_server_info(self.app.ctx)
                locs = len(self.app.ctx.checked_locations)
                total = self.app.ctx.total_locations
                new_width = self.width * (locs/total) if total > 0 else 0
                if new_width != self.p_width:
                    self.p_width = new_width
            else:
                self.p_width = 0
            await asyncio.sleep(30)

    def toggle_timer(self):
        """Toggle timer on/off (pause/resume)"""
        if self.timer is None or self.timer.ctx is None:
            return  # No timer (launcher role) or no game session hooked up
        if self.timer.is_running:
            self.timer.stop()  # Pause
        else:
            self.timer.start()  # Start or resume
    
    def reset(self, instance):
        """Reset the timer (called on long press)"""
        self.timer.reset()

    def ui_built(self):
        if self.timer is not None:
            self.timer.on_ui_built()
        self.server_info_label.on_ui_built()
    
    def update_server_info(self, ctx):
        """Update server info from on_connect - called from Gui.py"""
        self.server_info_label.update_server_info(ctx)
    
    def on_disconnect(self):
        """Handle disconnect - called from Gui.py"""
        self.server_info_label.on_disconnect()

    def open_profile(self):
        """Open user profile interface"""
        show_profile()

    def _open_builtin(self, name: str):
        """Trailing-icon shortcut to a builtin component (Website/Discord)."""
        from LauncherComponents import find_component
        component = find_component(name)
        if component and component.func:
            component.func()

    def enable_energy_link(self):
        self.energy_link_label.text = "Energy Link: Standby"

    def set_new_energy_link_value(self):
        self.energy_link_label.set_new_energy_link_value(self.ctx.current_energy_link_value)

class TopAppBarLayout(AnchorLayout):
    """
    Layers the progress overlay behind the transparent top app bar and
    keeps their size, position, and progress in sync.
    """
    
    top_appbar: ObjectProperty
    progress_overlay: ObjectProperty
    anchor_x = "left"
    anchor_y = "top"
    size_hint_x = 1
    padding = 0,39,0,0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Overlay first, so the transparent app bar draws over it.
        self.progress_overlay = ProgressOverlay()
        self.progress_overlay.size_hint = (None, None)
        self.add_widget(self.progress_overlay)
        
        self.top_appbar = TopAppBar()
        self.top_appbar.id = "top_appbar"
        self.add_widget(self.top_appbar)
        
        self.progress_overlay.size = self.top_appbar.size
        self.progress_overlay.pos = self.top_appbar.pos
        
        self.top_appbar.bind(p_width=self._update_progress_overlay)
        self.top_appbar.bind(size=self._update_progress_overlay_size)
        self.top_appbar.bind(pos=self._update_progress_overlay_pos)
    
    def _update_progress_overlay(self, instance, value):
        """Update progress overlay width when app bar progress changes"""
        self.progress_overlay.p_width = value
    
    def _update_progress_overlay_size(self, instance, value):
        """Update progress overlay size when app bar size changes"""
        self.progress_overlay.size = self.top_appbar.size
    
    def _update_progress_overlay_pos(self, instance, value):
        """Update progress overlay position when app bar position changes"""
        self.progress_overlay.pos = self.top_appbar.pos

