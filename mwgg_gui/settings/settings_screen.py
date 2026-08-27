from __future__ import annotations
"""
SETTINGS SCREEN

Creates the settings screen that will be displayed
when the user clicks the settings button in the
top right corner of the screen.
"""

__all__ = ("SettingsScreen", "register_settings_section")
from kivy.lang import Builder
from kivy.properties import ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.metrics import dp
import logging
import os

from kivymd.uix.screen import MDScreen
from kivymd.uix.navigationdrawer import MDNavigationDrawerDivider
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.navigationdrawer import MDNavigationLayout
from kivymd.uix.label import MDLabel

from mwgg_gui.components.nav_drawer import NavDrawerMenu, NavDrawerLabel, NavDrawerItem
from mwgg_gui.settings.settings_components import (
    ConnectionSettings,
    ThemingSettings,
    InterfaceSettings,
)

logger = logging.getLogger("Client")

settings_dict = {
    "Connection": [
        {"name": "Profile", "icon": "account"},
        {"name": "Hostname", "icon": "earth"},
        {"name": "Host Authentication", "icon": "shield-account"},
    ],
    "Theming": [
        {"name": "Dark/Light Mode", "icon": "theme-light-dark"},
        {"name": "Color Palette", "icon": "palette"},
        {"name": "Text Colors", "icon": "format-paint"},
        {"name": "Font Sizes", "icon": "format-font"}
    ],
    "Interface": [
        {"name": "Display", "icon": "monitor"},
        {"name": "Layout", "icon": "page-layout-sidebar-left"}
    ],
}

# External (world-contributed) sections registered via
# register_settings_section(). Keys are lowercased section names; values are
# {"title": str, "factory": Callable[[], MDBoxLayout], "items": [{"name": ..., "icon": ...}]}.
_dynamic_sections: dict = {}


def register_settings_section(name: str, title: str, factory, items: list | None = None) -> None:
    """Contribute a section to the global SettingsScreen.

    Intended for world clients (Universal Tracker, etc.) that want their own
    settings panel inside the launcher's Settings screen instead of bolting
    something onto their own tab.

    :param name: Single lowercase identifier; doubles as the screen_manager name
                 the nav-drawer items route to.
    :param title: Display label for the section header in the drawer.
    :param factory: Zero-arg callable returning the section's content widget.
                    Typically a ``SettingsScrollBox`` subclass instance.
    :param items: Optional nav-drawer items list (``[{"name": ..., "icon": ...}, ...]``).
                  Defaults to a single entry whose label is ``title`` and icon ``"tune"``.
    """
    key = name.lower()
    _dynamic_sections[key] = {
        "title": title,
        "factory": factory,
        "items": items or [{"name": title, "icon": "tune"}],
    }
    # If a SettingsScreen is already live, splice the section in now so the
    # user doesn't have to relaunch.
    try:
        from kivy.app import App
        app = App.get_running_app()
    except Exception:
        return
    if app is None:
        return
    screen = getattr(app, "settings_screen", None)
    if screen is None or not hasattr(screen, "add_dynamic_section"):
        return
    if key in screen.settings_screen_manager.screen_names:
        return
    screen.add_dynamic_section(key)

# Define custom widgets in kv language
KV = '''
SettingsNavLayout:
    size_hint_y: None
    height: Window.height-103
    settings_nav_menu: settings_nav_menu

    MDScreenManager:
        id: settings_screen_manager
    MDNavigationDrawer:
        id: settings_nav_drawer
        radius: 0, dp(16), dp(16), 0
        drawer_type: "standard"
        anchor: "left"
        elevation: 10
        md_bg_color: app.theme_cls.surfaceContainerLowColor
        
        MDBoxLayout:
            orientation: "vertical"
            spacing: dp(8)
            padding: [dp(4), dp(4), dp(4), dp(4)]
            
            FitImage:
                source: os.path.join(os.getenv("KIVY_DATA_DIR"), "images", "logo_bg.png")
                size_hint: None,None
                size: dp(256), dp(161)
                pos_hint: {"center_x": 0.5, "top": 1}
            
            NavDrawerMenu:
                id: settings_nav_menu


<SettingsScreenSection>:
    orientation: "vertical"
    size_hint_y: None
    pos_hint: {"center_x": 0.5}
    height: Window.height-103
    md_bg_color: app.theme_cls.backgroundColor
'''

class SettingsNavLayout(MDNavigationLayout):
    settings_nav_menu: ObjectProperty

class SettingsScreenSection(MDScreen):
    '''
    Generic settings section screen
    For use only on the settings screen, not as a standalone screen
    '''
    name = StringProperty("")
    title = StringProperty("")
    nav_drawer = ObjectProperty(None)

    def __init__(self, name, title, nav_drawer, **kwargs):
        super().__init__(**kwargs)
        logger.debug(f"Initializing SettingsScreenSection: {name}")
        self.nav_drawer = nav_drawer
        self.name = name
        self.title = title
        Clock.schedule_once(lambda x: self.nav_drawer.set_state("open"))
        
        # Create the appropriate settings component based on the section name
        try:
            key = name.lower()
            logger.debug(f"Creating settings component for section: {key}")
            if key == "connection":
                logger.debug("Creating ConnectionSettings component")
                self.add_widget(ConnectionSettings())
            elif key == "theming":
                logger.debug("Creating ThemingSettings component")
                self.add_widget(ThemingSettings())
            elif key == "interface":
                logger.debug("Creating InterfaceSettings component")
                self.add_widget(InterfaceSettings())
            elif key in _dynamic_sections:
                logger.debug(f"Creating dynamic settings component: {key}")
                self.add_widget(_dynamic_sections[key]["factory"]())
            else:
                logger.warning(f"Unknown section name: {key}. Expected one of: connection, theming, interface, or a registered dynamic section.")
                # Add a placeholder widget with a warning message
                warning_box = MDBoxLayout(orientation="vertical", padding=dp(16))
                warning_box.add_widget(MDLabel(
                    text=f"Unknown section: {name}",
                    theme_text_color="Error"
                ))
                self.add_widget(warning_box)
        except Exception as e:
            logger.error(f"Error creating settings component for {name}: {e}", exc_info=True)
            # Add an error widget
            error_box = MDBoxLayout(orientation="vertical", padding=dp(16))
            error_box.add_widget(MDLabel(
                text=f"Error loading section: {name}",
                theme_text_color="Error"
            ))
            self.add_widget(error_box)

class SettingsScreen(MDScreen):
    '''
    Main settings screen to call from the application
    '''
    settings_nav_drawer: ObjectProperty
    settings_screen_manager: MDScreenManager
    nav_layout: SettingsNavLayout
    nav_menu: NavDrawerMenu
    

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.debug("Initializing SettingsScreen")
        self.name = "settings"
        self.nav_layout = Builder.load_string(KV)
        logger.debug(f"Loaded nav_layout: {self.nav_layout}")
        
        self.settings_nav_drawer = self.nav_layout.ids.settings_nav_drawer
        self.settings_nav_drawer.type = "standard"
        logger.debug(f"Retrieved nav_drawer: {self.settings_nav_drawer}")
        
        self.settings_screen_manager = self.nav_layout.ids.settings_screen_manager
        self.setup_sections()
        logger.debug(f"Retrieved screen_manager: {self.settings_screen_manager}")
        
        self.add_widget(self.nav_layout)
        
        logger.debug("Added nav_layout to screen")
        
        # Set up the navigation menu after everything else is initialized
        Clock.schedule_once(self.setup_navigation_menu)
    
    def setup_sections(self, *args):
        logger.debug("Setting up settings sections")
        for section in settings_dict:
            logger.debug(f"Adding section: {section}")
            section_name = section.lower()
            logger.debug(f"Section name (lowercase): {section_name}")
            self.settings_screen_manager.add_widget(SettingsScreenSection(name=section_name, title=section, nav_drawer=self.settings_nav_drawer))
        # World-contributed sections (e.g. Universal Tracker) registered before
        # the screen was built.
        for key, info in _dynamic_sections.items():
            if key in self.settings_screen_manager.screen_names:
                continue
            logger.debug(f"Adding dynamic section: {key} ({info['title']})")
            self.settings_screen_manager.add_widget(SettingsScreenSection(
                name=key, title=info["title"], nav_drawer=self.settings_nav_drawer,
            ))
        self.settings_screen_manager.current = "interface"
        logger.debug("Finished setting up sections")

    def setup_navigation_menu(self, *args):
        """Set up the navigation menu with all its items."""
        logger.debug("Setting up navigation menu")
        self.nav_menu = self.nav_layout.settings_nav_menu
        self.nav_menu.on_start()

        for screen_name in self.settings_screen_manager.screen_names:
            logger.debug(f"Adding menu item for screen: {screen_name}")
            # Resolve which menu-items list applies: built-in via settings_dict,
            # otherwise the dynamic registration.
            if screen_name.capitalize() in settings_dict:
                title = screen_name.capitalize()
                items = settings_dict[title]
            else:
                info = _dynamic_sections.get(screen_name)
                if info is None:
                    logger.warning(f"No menu items found for screen {screen_name}; skipping")
                    continue
                title = info["title"]
                items = info["items"]

            # Add section header
            self.nav_menu.add_widget(NavDrawerLabel(text=title))

            for item in items:
                logger.debug(f"Adding menu item: {item['name']}")
                self.nav_menu.add_widget(NavDrawerItem(
                    manager=self.settings_screen_manager,
                    icon=item["icon"],
                    text=item["name"],
                    screen=screen_name
                ))

            # Divider between sections (skip after the last one to avoid a
            # stray separator at the bottom).
            self.nav_menu.add_widget(MDNavigationDrawerDivider())
        logger.debug("Finished setting up navigation menu")

    def add_dynamic_section(self, name: str) -> None:
        """Splice a section registered AFTER this screen was built into the
        live nav menu. Called by ``register_settings_section`` when it detects
        an active SettingsScreen on the app."""
        key = name.lower()
        info = _dynamic_sections.get(key)
        if info is None:
            return
        if key in self.settings_screen_manager.screen_names:
            return
        section = SettingsScreenSection(
            name=key, title=info["title"], nav_drawer=self.settings_nav_drawer,
        )
        self.settings_screen_manager.add_widget(section)
        if getattr(self, "nav_menu", None) is None:
            return
        self.nav_menu.add_widget(NavDrawerLabel(text=info["title"]))
        for item in info["items"]:
            self.nav_menu.add_widget(NavDrawerItem(
                manager=self.settings_screen_manager,
                icon=item["icon"],
                text=item["name"],
                screen=key,
            ))
        self.nav_menu.add_widget(MDNavigationDrawerDivider())
