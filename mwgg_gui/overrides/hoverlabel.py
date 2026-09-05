from __future__ import annotations

from kivymd.uix.label import MDLabel
from kivymd.uix.behaviors import HoverBehavior
from kivy.core.text.markup import MarkupLabel
from kivy.properties import StringProperty, NumericProperty, ColorProperty
from kivy.utils import get_color_from_hex

import re

# TEXT_COLORS values are bare 6-digit hex; kivy's hex_colormap carries "#".
_color_tag = re.compile(r"\[color=#?([0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?)]")


def ref_span_color(text: str, key: str) -> list[float] | None:
    """RGBA of the color tag opening the span ``key``'s ref wraps, or None when uncolored."""
    open_tag = f"[ref={key}]"
    start = text.find(open_tag)
    if start < 0:
        return None
    match = _color_tag.match(text, start + len(open_tag))
    return get_color_from_hex(match.group(1)) if match else None

class HoverLabel(MDLabel):

    mw_id: NumericProperty = 0
    mw_ref: StringProperty = ""
    mw_color = ColorProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.markup = True
        self.register_event_type('on_ref_hover')
        self.bind(refs=self._on_ref_set)

    def _on_ref_set(self, *args):
        try:
            for key in self.refs.keys():
                if len(self.refs) == 1:
                    ref_name = key
                    self.mw_id, self.mw_ref = ref_name.split("|", maxsplit=1)
                    self.mw_color = ref_span_color(self.text, ref_name)
                    if "<br>" in self.mw_ref:
                        self.mw_ref = self.mw_ref.split("<br>", maxsplit=1)[0]
            return True
        except IndexError:
            return False     

    def on_enter(self):
        if self.hover_visible:
            self.dispatch('on_ref_hover', self.refs)
        return super().on_enter()

    def on_ref_hover(self, ref):
        pass

class SimpleHoverLabel(HoverBehavior, MarkupLabel):
    mw_id: NumericProperty = 0
    mw_ref: StringProperty = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_ref_hover')
        self.bind(refs=self._on_ref_set)

    def _on_ref_set(self, *args):
        try:
            for key in self.refs.keys():
                if len(self.refs) == 1:
                    ref_name = key
                    self.mw_id, self.mw_ref = ref_name.split("|", maxsplit=1)
                    if "<br>" in self.mw_ref:
                        self.mw_ref = self.mw_ref.split("<br>", maxsplit=1)[0]
            return True
        except IndexError:
            return False     

    def on_enter(self):
        if self.hover_visible:
            self.dispatch('on_ref_hover', self.refs)
        return super().on_enter()

    def on_ref_hover(self, ref):
        pass