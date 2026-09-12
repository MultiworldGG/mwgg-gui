"""
TourOverlay: plays a first-launch tour (steps in components/onboarding.py)
over the live UI. A scrim covers the window below the titlebar with a hole
cut over the current step's spotlight; touches inside the hole reach the
widgets underneath, touches elsewhere are swallowed, and a card beside the
hole carries the step text with Back/Next/Skip.

The app supplies the spotlights: `targets(key)` returns the live widgets
(or window-space (x, y, w, h) tuples) for a step's target key. It is read
every frame so the hole follows layout, scrolling and an opening drawer.
"""
from __future__ import annotations

__all__ = ("TourOverlay", "TourCard")

from typing import Callable, Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import (Color, Line, Rectangle, RoundedRectangle,
                           StencilPop, StencilPush, StencilUnUse, StencilUse)
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.floatlayout import FloatLayout
from kivymd.app import MDApp
from kivymd.uix.card import MDCard

from mwgg_gui.components.onboarding import TourStep, place_card, spotlight_rect, union_rect

SCRIM_ALPHA = 0.7
HOLE_PAD = dp(6)
HOLE_RADIUS = dp(12)
CARD_MARGIN = dp(16)

Builder.load_string('''
<TourCard>:
    orientation: "vertical"
    style: "elevated"
    size_hint: None, None
    width: dp(340)
    height: self.minimum_height
    padding: dp(20), dp(16)
    spacing: dp(8)
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.surfaceContainerHighColor
    MDLabel:
        text: root.step_label
        adaptive_height: True
        text_size: self.width, None
        font_style: "Label"
        role: "small"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceVariantColor
    MDLabel:
        text: root.title
        adaptive_height: True
        text_size: self.width, None
        font_style: "Title"
        role: "medium"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceColor
    MDLabel:
        text: root.body
        adaptive_height: True
        text_size: self.width, None
        font_style: "Body"
        role: "medium"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceColor
    MDBoxLayout:
        adaptive_height: True
        spacing: dp(8)
        padding: 0, dp(8), 0, 0
        MDButton:
            style: "text"
            on_release: root.overlay.skip()
            MDButtonText:
                text: "Skip tour"
        Widget:
        MDButton:
            style: "text"
            disabled: root.first
            on_release: root.overlay.back()
            MDButtonText:
                text: "Back"
        MDButton:
            style: "filled"
            on_release: root.overlay.next()
            MDButtonText:
                text: "Done" if root.last else "Next"
''')


class TourCard(MDCard):
    overlay = ObjectProperty(None)
    step_label = StringProperty("")
    title = StringProperty("")
    body = StringProperty("")
    first = BooleanProperty(True)
    last = BooleanProperty(False)


class TourOverlay(FloatLayout):
    """See the module docstring. Lives directly on the app's root layout,
    so its coordinates are window coordinates."""
    active = BooleanProperty(False)
    step_index = NumericProperty(-1)

    def __init__(self, targets: Callable[[str], list],
                 on_step: Optional[Callable[[Optional[str]], None]] = None, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.targets = targets
        self.on_step = on_step
        self.size_hint = (None, None)
        self.steps: tuple[TourStep, ...] = ()
        self._on_finish = None
        self._hole = None
        self._track_event = None
        with self.canvas.before:
            StencilPush()
            self._hole_shape = RoundedRectangle(pos=(0, 0), size=(0, 0), radius=[HOLE_RADIUS])
            # Paint where the stencil is NOT the hole: the scrim with a cutout.
            StencilUse(func_op="notequal")
            self._scrim_color = Color(rgba=(0, 0, 0, 0))
            self._scrim = Rectangle(pos=self.pos, size=self.size)
            StencilUnUse()
            self._hole_shape_undo = RoundedRectangle(pos=(0, 0), size=(0, 0), radius=[HOLE_RADIUS])
            StencilPop()
            self._ring_color = Color(rgba=(0, 0, 0, 0))
            self._ring = Line(width=dp(2), rounded_rectangle=(0, 0, 2, 2, 1))
        self.bind(pos=self._sync_scrim, size=self._sync_scrim)
        self.card = TourCard(overlay=self)
        self.add_widget(self.card)

    def _sync_scrim(self, *_args):
        self._scrim.pos = self.pos
        self._scrim.size = self.size

    def start(self, steps, on_finish: Optional[Callable[[], None]] = None) -> None:
        self.steps = tuple(steps)
        self._on_finish = on_finish
        theme = self.app.theme_cls
        self._scrim_color.rgba = (*theme.surfaceColor[:3], SCRIM_ALPHA)
        self._ring_color.rgba = theme.primaryColor
        self.active = True
        if self._track_event is None:
            self._track_event = Clock.schedule_interval(self._track, 0)
        self._show_step(0)

    def next(self) -> None:
        if self.step_index + 1 >= len(self.steps):
            self.finish()
        else:
            self._show_step(self.step_index + 1)

    def back(self) -> None:
        if self.step_index > 0:
            self._show_step(self.step_index - 1)

    def skip(self) -> None:
        self.finish()

    def finish(self) -> None:
        if not self.active:
            return
        self.active = False
        if self._track_event is not None:
            self._track_event.cancel()
            self._track_event = None
        self.step_index = -1
        if self.on_step is not None:
            self.on_step(None)
        if self._on_finish is not None:
            self._on_finish()

    def _show_step(self, index: int) -> None:
        self.step_index = index
        step = self.steps[index]
        card = self.card
        card.step_label = f"{index + 1} of {len(self.steps)}"
        card.title = step.title
        card.body = step.text(self.app.layout_mode.compact)
        card.first = index == 0
        card.last = index == len(self.steps) - 1
        if self.on_step is not None:
            self.on_step(step.target)
        self._track(0)

    def _bounds(self) -> tuple[float, float, float, float]:
        """Window minus the custom titlebar, whose controls stay usable."""
        title_bar = getattr(self.app, "title_bar", None)
        if title_bar is not None and title_bar.parent is not None:
            top = title_bar.y
        else:
            top = Window.height
        return 0.0, 0.0, float(Window.width), float(top)

    def _track(self, _dt) -> None:
        bounds = self._bounds()
        if (self.x, self.y, self.width, self.height) != bounds:
            self.pos = bounds[:2]
            self.size = bounds[2:]
        hole = self._spotlight(bounds)
        if hole != self._hole:
            self._hole = hole
            self._paint_hole(hole)
        pos = place_card((self.card.width, self.card.height), bounds, hole, CARD_MARGIN)
        if (self.card.x, self.card.y) != pos:
            self.card.pos = pos

    def _spotlight(self, bounds):
        if not 0 <= self.step_index < len(self.steps):
            return None
        key = self.steps[self.step_index].target
        if not key:
            return None
        rects = []
        for item in self.targets(key):
            if isinstance(item, tuple):
                rects.append(item)
            elif item is not None and item.get_root_window() is not None:
                x, y = item.to_window(*item.pos)
                rects.append((x, y, item.width, item.height))
        rect = union_rect(rects)
        if rect is None:
            return None
        return spotlight_rect(rect, HOLE_PAD, bounds)

    def _paint_hole(self, hole) -> None:
        if hole is None or hole[2] <= 0 or hole[3] <= 0:
            for shape in (self._hole_shape, self._hole_shape_undo):
                shape.size = (0, 0)
            self._ring_color.a = 0
            return
        x, y, w, h = hole
        radius = min(HOLE_RADIUS, w / 2, h / 2)
        for shape in (self._hole_shape, self._hole_shape_undo):
            shape.pos = (x, y)
            shape.size = (w, h)
            shape.radius = [radius]
        self._ring.rounded_rectangle = (x, y, w, h, radius)
        self._ring_color.a = 1

    def _in_hole(self, x: float, y: float) -> bool:
        hole = self._hole
        return (hole is not None and hole[0] <= x <= hole[0] + hole[2]
                and hole[1] <= y <= hole[1] + hole[3])

    def on_touch_down(self, touch):
        if not self.active:
            return False
        if self.card.collide_point(*touch.pos):
            touch.ud["tour_card"] = True
            super().on_touch_down(touch)
            return True
        if not self.collide_point(*touch.pos) or self._in_hole(*touch.pos):
            return False
        touch.ud["tour_blocked"] = True
        return True

    def on_touch_move(self, touch):
        if touch.ud.get("tour_card"):
            super().on_touch_move(touch)
            return True
        return bool(touch.ud.get("tour_blocked"))

    def on_touch_up(self, touch):
        if touch.ud.get("tour_card"):
            super().on_touch_up(touch)
            return True
        return bool(touch.ud.get("tour_blocked"))
