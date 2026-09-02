"""KivyMD 2.0.0 ripple FBO fix.

The 2.0.0 tag builds the M3 ripple FBO at the widget's construction-time size,
which is zero-height for anything sized by ``minimum_height`` before it has
children (MDSnackbar, adaptive cards) and fails with
``FBO Initialization failed: Incomplete attachment``. Upstream fixed it in
kivymd/KivyMD@0b8de39 by starting at a fixed size and resizing lazily; this
module ports that commit and is a no-op on any other version.
"""
from __future__ import annotations

import kivymd
from kivy.graphics import ClearBuffers, ClearColor, Color, Fbo, Rectangle
from kivymd.uix.behaviors.ripple_behavior import M3CommonRipple

__all__ = ("patch_ripple_fbo",)

_PATCH_VERSION = "2.0.0"
_INITIAL_SIZE = (50, 50)


def _init_fbos(self: M3CommonRipple) -> None:
    self._phase = 0.0
    self.ripple_pos = (0, 0)
    self.fbo = Fbo(size=_INITIAL_SIZE, group="m3_ripple_behavior")
    self.set_shader(self.fbo)

    with self.fbo:
        ClearColor(0, 0, 0, 0)
        ClearBuffers()
        Color(1, 1, 1, 1)
        self.rect = Rectangle(pos=(0, 0), size=_INITIAL_SIZE)


def patch_ripple_fbo() -> bool:
    if kivymd.__version__ != _PATCH_VERSION or M3CommonRipple.init_fbos is _init_fbos:
        return False
    original_update_uniforms = M3CommonRipple._update_uniforms

    def _update_uniforms(self: M3CommonRipple) -> None:
        if self.fbo.size != self.size:
            self.fbo.size = self.size
        original_update_uniforms(self)

    M3CommonRipple.init_fbos = _init_fbos
    M3CommonRipple._update_uniforms = _update_uniforms
    return True


patch_ripple_fbo()
