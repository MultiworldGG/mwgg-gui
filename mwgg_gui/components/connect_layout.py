"""
Legacy kvui `connect_layout`: the connect bar worlds append status widgets and
buttons to (WarioWare's flower count, DKC's barrel counter, Manual's DeathLink
button). The current screen's BottomAppBar hosts it: in the standard bar it
grows left from the FAB and the slide-up text input gives up width to it. In
Compact Mode, or when the widgets would squeeze that input below its minimum,
it is a full-width bar above the bottom bar that takes no room while empty.
"""
from __future__ import annotations

__all__ = ("ConnectLayout", "CONNECT_BAR_HEIGHT")

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty
from kivymd.uix.boxlayout import MDBoxLayout

from mwgg_gui.components.layout_mode import get_layout_mode

CONNECT_BAR_HEIGHT = dp(48)

Builder.load_string('''
<ConnectLayout>:
    orientation: "horizontal"
    spacing: dp(8)
    theme_bg_color: "Custom"
    md_bg_color:
        app.theme_cls.transparentColor if not root.full_bar else \
        app.theme_cls.primaryContainerColor if app.theme_cls.theme_style == "Light" \
        else app.theme_cls.onPrimaryColor
''')


class ConnectLayout(MDBoxLayout):
    # Set by the hosting BottomAppBar.
    full_bar = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.bind(children=self._fit, minimum_width=self._fit, full_bar=self._fit)
        self._fit()

    @property
    def content_width(self) -> float:
        return self.minimum_width - self.padding[0] - self.padding[2]

    def _fit(self, *_args) -> None:
        shown = bool(self.children)
        self.opacity = 1 if shown else 0
        if self.full_bar:
            self.padding = (dp(16), 0)
            self.size_hint_x = 1
            self.height = CONNECT_BAR_HEIGHT if shown else 0
        else:
            self.padding = (0, 0)
            self.size_hint_x = None
            self.width = self.minimum_width
            self.height = CONNECT_BAR_HEIGHT
        get_layout_mode().connect_bar_height = self.height if self.full_bar else 0
