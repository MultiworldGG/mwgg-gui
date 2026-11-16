"""KivyMD 2.0.0 hint text position for non-default text field heights.

``MDTextField`` offsets its hint text for its ``dp(56)`` default height, so the
``dp(40)`` fields from mw_theme.kv rest the hint above center and float it past
the top edge. Every hint target goes through ``set_pos_hint_text``; this module
shifts it by half the height difference, keeping the resting hint's offset from
center and the floating hint's offset from the top edge at their ``dp(56)``
values.
"""
from __future__ import annotations

from kivy.animation import Animation
from kivy.metrics import dp
from kivymd.uix.textfield import MDTextField

__all__ = ("patch_hint_text_position",)


def set_pos_hint_text(self: MDTextField, y: float, x: float) -> None:
    y += (dp(56) - self.height) / 2
    Animation(_hint_y=y, _hint_x=x, d=0.2, t="out_quad").start(self)


def patch_hint_text_position() -> bool:
    if MDTextField.set_pos_hint_text is set_pos_hint_text:
        return False
    MDTextField.set_pos_hint_text = set_pos_hint_text
    return True


patch_hint_text_position()
