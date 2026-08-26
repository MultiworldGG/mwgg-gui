"""
SafeEffectWidget - EffectWidget that tolerates degenerate (zero) sizes.

Kivy's EffectWidget.refresh_fbo_setup resizes its FBOs to self.size on every
size dispatch. Layout passes can dispatch a transient zero dimension - e.g.
the custom titlebar's float layout sizes TitleBlur to (0, 40) while
Window.set_custom_titlebar's SWP_FRAMECHANGED re-enters the event loop
mid-layout - and a zero-size texture attachment fails FBO creation on strict
drivers (NVIDIA: "Incomplete attachment (36054)"), killing the Kivy main loop.
Skipping the refresh is safe: the size binding fires again once layout
assigns a real size.
"""
from __future__ import annotations
__all__ = ("SafeEffectWidget",)

from kivy.uix.effectwidget import EffectWidget


class SafeEffectWidget(EffectWidget):
    def refresh_fbo_setup(self, *args):
        if self.width < 1 or self.height < 1:
            return
        super().refresh_fbo_setup(*args)
