"""
Shared navigation-drawer menu widgets, used by the settings screen's
always-open drawer and the launcher's toggled drawer.

The kv rules live here and load exactly once at import: defining them
again in another kv source would apply each rule twice and double every
item's child widgets.
"""
from __future__ import annotations

__all__ = ("NavDrawerMenu", "NavDrawerLabel", "NavDrawerItem")

import logging

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.navigationdrawer import MDNavigationDrawerMenu
from kivymd.uix.navigationdrawer.navigationdrawer import (
    MDNavigationDrawerItem,
    MDNavigationDrawerLabel,
)

logger = logging.getLogger("Client")

Builder.load_string('''
<NavDrawerMenu>:
    orientation: "vertical"

<NavDrawerLabel>:
    font_style: "Title"
    bold: True
    padding: [0, dp(16), 0, 0]
    theme_text_color: "Custom"
    text_color: app.theme_cls.primaryColor

<NavDrawerItem>:
    MDNavigationDrawerItemLeadingIcon:
        icon: root.icon
        theme_icon_color: "Custom"
        icon_color: app.theme_cls.onPrimaryContainerColor
    MDNavigationDrawerItemText:
        text: root.text
        shorten: True
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSecondaryContainerColor
    MDNavigationDrawerItemTrailingText:
        text: root.trailing_text
        width: dp(32)
        theme_text_color: "Custom"
        text_color: app.theme_cls.onTertiaryContainerColor
''')


class NavDrawerMenu(MDNavigationDrawerMenu):
    menu_label = StringProperty("")

    def on_start(self):
        self.ids.menu.size_hint_x = None
        self.ids.menu.width = self.width - dp(8)


class NavDrawerLabel(MDNavigationDrawerLabel):
    """
    Section header label (Connection, Theming, Tools, ...)

    TODO: This isn't quite right, needs to be redesigned
    """
    pass


class NavDrawerItem(MDNavigationDrawerItem):
    """
    Screen-navigation item (Hostname, Host Authentication, etc.)
    """
    icon = StringProperty("")
    text = StringProperty("")
    trailing_text = StringProperty("")
    screen = StringProperty("")
    manager = ObjectProperty(None)

    def __init__(self, manager, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = manager
        self.bind(on_release=self.screen_callback)

    def screen_callback(self, *args):
        try:
            logger.debug(f"Navigating to screen: {self.screen}")
            self.manager.current = self.screen
            logger.debug("Navigation complete")
        except Exception as e:
            logger.error(f"Error during navigation: {e}", exc_info=True)
