from __future__ import annotations
"""
LauncherSliverAppbar: class that provides the games list on the launcher screen

Includes the following:
- SearchBar - search bar for the launcher screen
- LauncherTextField - text field for the search bar
"""
__all__ = ('LauncherSliverAppbar', 'SearchBar', 'LauncherTextField')

from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.clock import Clock
from kivy.app import App
from kivy.lang import Builder
from kivymd.uix.sliverappbar import MDSliverAppbar, MDSliverAppbarContent
from kivymd.uix.appbar import (MDTopAppBar,
                               MDTopAppBarTrailingButtonContainer,
                               MDActionTopAppBarButton)
from kivymd.uix.textfield import MDTextField

Builder.load_string('''
#:import os os
<LauncherSliverAppbar>:
    pos_hint: {"x": 0, "top": 1}
    width: dp(260)
    padding: 0
    size_hint_x: None
    adaptive_height: True
    hide_appbar: True
    background_color: app.theme_cls.secondaryContainerColor
    MDSliverAppbarHeader:
        Image:
            source: os.path.join(os.getenv("KIVY_DATA_DIR"), "images", "logo_bg.png")
            pos_hint: {"center_y": 0.55}
            fit_mode: "scale-down"
    SearchBar:
        id: games_search_bar
                    
<SearchBar>:
    type: "small"
    height: dp(74)
    padding: dp(10), dp(0), dp(10), dp(0)

<LauncherTextField>:
    -height: dp(56)
    theme_font_name: "Custom"
    theme_font_style: "Custom"
    font_name: app.theme_cls.font_styles[self.font_style][self.role]["font-name"]
    font_size: app.theme_cls.font_styles[self.font_style][self.role]["font-size"]
    MDTextFieldHintText:
        text: root.hint_text
        theme_font_name: "Custom"
        theme_font_style: "Custom"
        font_name: app.theme_cls.font_styles[self.font_style][self.role]["font-name"]
        font_size: app.theme_cls.font_styles[self.font_style][self.role]["font-size"]
''')

class LauncherSliverAppbar(MDSliverAppbar):
    '''
    Games list on the launcher screen
    '''
    content: MDSliverAppbarContent

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.content = MDSliverAppbarContent(orientation="vertical", padding=0)
        self.content.id = "content"
        self.add_widget(self.content)
        self.ids.scroll.y = dp(50)
        self.ids.scroll.bar_width = dp(10)
        self.ids.scroll.scroll_type = ["bars", "content"]
        self.ids.header.pos_hint = {"top": 1}

class LauncherTextField(MDTextField):
    hint_text = StringProperty("")
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hint_text = kwargs.get("hint_text", "")

class SearchBar(MDTopAppBar):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_box = LauncherTextField(
            id="game_tag_filter",
            hint_text = "Game Search",
            pos_hint = {"center_y": 0.5}
        )
        self.add_widget(self.search_box)
        self.search_box.bind(on_text_validate=self.on_enter)
        self.reset_button = MDActionTopAppBarButton(icon="restore")
        self.reset_button.bind(on_release=self.on_reset)
        self.add_widget(MDTopAppBarTrailingButtonContainer(self.reset_button))

    def add_widget(self, widget):
        if isinstance(widget, MDTextField):
            widget._appbar = self
            self.appbar_title = widget
            Clock.schedule_once(lambda x: self._add_title(widget))
        else:
            super().add_widget(widget)

    def _add_title(self, widget):
        super()._add_title(widget)

    def on_enter(self, instance):
        self._apply_search(instance.text, show_list=True)

    def on_reset(self, *args):
        self.search_box.text = ""
        self._apply_search("", show_list=False)

    def _apply_search(self, query: str, show_list: bool):
        """`show_list` drives Compact Mode's play/list flip: Enter brings
        the game list up, the clear button puts it away."""
        screen = App.get_running_app().screen_manager.current_screen
        # Import here to avoid circular import
        from .launcher import LauncherScreen
        if isinstance(screen, LauncherScreen):
            screen.apply_game_search(query, show_list)
