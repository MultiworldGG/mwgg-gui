"""
Progress Overlay Widget

A transparent overlay widget that displays a progress bar with proper background.
Designed to be positioned over an app bar to show completion progress while
allowing touch events to pass through to underlying widgets.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.properties import (
    NumericProperty,
    ReferenceListProperty,
)

__all__ = ("ProgressOverlay",)

Builder.load_string('''
<ProgressOverlay>:
    canvas:
        # Background rectangle (full app bar size)
        Color:
            rgba: app.theme_cls.surfaceColor
        Rectangle:
            pos: self.pos
            size: self.size
        # Progress rectangle (partial width)
        Color:
            rgba: app.theme_cls.surfaceBrightColor
        Rectangle:
            pos: self.pos
            size: self.prog_size
        # Shadow rectangle helps the progress standout
        Color:
            rgba: [0, 0, 0, 0.3]
        Rectangle:
            pos: self.x, self.y+2
            size: self.p_width, self.height-4
''')


class ProgressOverlay(Widget):
    """
    Progress bar drawn behind an app bar: a full-size background rectangle
    plus a progress rectangle sized by prog_size = (p_width, height).
    Transparent to touch events so the app bar stays interactive.
    """
    
    p_width: NumericProperty = NumericProperty(0)
    height: NumericProperty = NumericProperty(64)
    prog_size: ReferenceListProperty = ReferenceListProperty(p_width, height)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prog_size = (self.p_width, self.height)
    
    def on_touch_down(self, touch):
        return False
    
    def on_touch_move(self, touch):
        return False
    
    def on_touch_up(self, touch):
        return False
