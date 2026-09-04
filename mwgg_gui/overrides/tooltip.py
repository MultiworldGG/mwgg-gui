"""KivyMD 2.0.0 rich tooltip display fix.

``MDTooltip.display_tooltip`` in the 2.0.0 tag (and master as of 2026-09-03)
skips tooltips whose ``text`` is empty by reading ``self._tooltip.text``.
``MDTooltipRich`` is a BoxLayout with no ``text`` attribute, so hovering any
rich-tooltip widget raises ``AttributeError`` inside a Clock callback and kills
the Kivy loop. This module re-applies the same guard with ``getattr`` and is a
no-op once ``MDTooltipRich`` grows a ``text`` attribute upstream.
"""
from __future__ import annotations

from kivy.clock import Clock
from kivy.core.window import Window
from kivymd.material_resources import DEVICE_TYPE
from kivymd.uix.tooltip import MDTooltip, MDTooltipRich

__all__ = ("patch_rich_tooltip_display",)


# Keeps the upstream name: Clock re-resolves scheduled bound methods by
# __func__.__name__ on the instance.
def display_tooltip(self: MDTooltip, *args) -> None:
    tooltip = self._tooltip
    if not tooltip or tooltip.parent or not getattr(tooltip, "text", True):
        return
    Window.add_widget(tooltip)
    tooltip.pos = self.adjust_tooltip_position()
    delay = self.tooltip_display_delay if DEVICE_TYPE == "desktop" else 0
    Clock.schedule_once(self.animation_tooltip_show, delay)


def patch_rich_tooltip_display() -> bool:
    if hasattr(MDTooltipRich, "text") or MDTooltip.display_tooltip is display_tooltip:
        return False
    MDTooltip.display_tooltip = display_tooltip
    return True


patch_rich_tooltip_display()
