"""
SafeEffectWidget - EffectWidget that tolerates degenerate (zero) sizes and
redraws only when its content or size changes.

Kivy's EffectWidget.refresh_fbo_setup resizes its FBOs to self.size on every
size dispatch. Layout passes can dispatch a transient zero dimension - e.g.
the custom titlebar's float layout sizes TitleBlur to (0, 40) while
Window.set_custom_titlebar's SWP_FRAMECHANGED re-enters the event loop
mid-layout - and a zero-size texture attachment fails FBO creation on strict
drivers (NVIDIA: "Incomplete attachment (36054)"), killing the Kivy main loop.
Skipping the refresh is safe: the size binding fires again once layout
assigns a real size.

Kivy's private _update_glsl runs every Clock tick and writes a new `time`
uniform, which dirties the canvas and forces a full redraw and buffer swap
per tick. mwgg effects are static (blur and pixelate read only `resolution`),
so `time` is never written; a `time`-driven effect would render frozen.
"""
from __future__ import annotations
__all__ = ("SafeEffectWidget",)

from kivy.uix.effectwidget import EffectWidget


class SafeEffectWidget(EffectWidget):
    def refresh_fbo_setup(self, *args):
        if self.width < 1 or self.height < 1:
            return
        super().refresh_fbo_setup(*args)

    def _update_glsl(self, *largs):
        # Uniform writes flag a redraw only when the value changes.
        resolution = [float(size) for size in self.size]
        self.canvas["resolution"] = resolution
        for fbo in self.fbo_list:
            fbo["resolution"] = resolution
