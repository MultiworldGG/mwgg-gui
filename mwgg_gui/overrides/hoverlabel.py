from __future__ import annotations

from kivymd.uix.label import MDLabel
from kivy.properties import StringProperty, NumericProperty

class HoverLabel(MDLabel):

    mw_id: NumericProperty = 0
    mw_ref: StringProperty = ""

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