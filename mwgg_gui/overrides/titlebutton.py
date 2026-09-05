from __future__ import annotations
from kivy.lang import Builder
from kivymd.uix.behaviors.elevation import CommonElevationBehavior
from kivymd.uix.appbar import MDTopAppBarTitle

Builder.load_string('''
<-ButtonMDTopAppBarTitle>:
    color:
        self.text_color \
        if self.text_color else \
        self.theme_cls.onSurfaceColor
    text_size:
        (self.width if not self.adaptive_width else None) \
        if not self.adaptive_size else None, \
        None
    font_size:
        self.theme_cls.font_styles[self.font_style][self.role]["font-size"] \
        if self.theme_font_size == "Primary" else self.font_size
    line_height:
        self.theme_cls.font_styles[self.font_style][self.role]["line-height"] \
        if self.theme_line_height == "Primary" else self.line_height
    font_name:
        self.theme_cls.font_styles[self.font_style][self.role]["font-name"] \
        if self.theme_font_name == "Primary" else self.font_name
    canvas:
        Color:
            rgba: 0,0,0,.3
        RoundedRectangle:
            size: (self.width-14, self.height-14)
            pos: (self.x+7, self.y+7)
            radius: [15,]
    Label:
        text: root.text
        size: root.size
        pos: root.pos
        color: root.color

''')

class ButtonMDTopAppBarTitle(MDTopAppBarTitle):
    pass