"""
InnerMDScreen: MDScreen with a chrome-aware inner content area.

The root layout layers the title bar and top app bar over the screen
manager, so a bare `MDScreen`'s children overlap the chrome. The fix
can't shrink the screen itself: `MDScreenManager` transitions
(`SwapTransition` and friends) look uniform only when every screen is
full-window size. So the screen stays at `(1, 1)` and `add_widget` is
proxied into an inner content layout positioned for the chrome (via the
`AutoAdjustHeightBehavior` mixin, like every other screen); use
`add_overlay` for window-edge widgets such as a `BottomAppBar`. Set
`adjust_bottom_appbar = False` on screens without a bottom app bar.

NOTE: intentionally *not* re-exported from `overrides/__init__.py` --
`mw_theme.py` imports from `overrides` during its own initialization,
and pulling `AutoAdjustHeightBehavior` from `mw_theme` there would
deadlock the cycle. Import the class directly:

    from mwgg_gui.overrides.innermdscreen import InnerMDScreen
"""
from __future__ import annotations

__all__ = ("InnerMDScreen",)

from kivy.properties import ObjectProperty
from kivymd.theming import ThemableBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screen import MDScreen

from mwgg_gui.components.mw_theme import AutoAdjustHeightBehavior


class _InnerContent(AutoAdjustHeightBehavior, MDBoxLayout):
    """Chrome-aware content area. `size_hint_y` auto-adjusts to leave
    room for the title bar, top app bar, and (optionally) the bottom
    app bar; `y` is offset so the bottom bar fits beneath it."""
    adjust_title_bar = True
    adjust_app_bar = True
    adjust_bottom_appbar = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_x = 1


class InnerMDScreen(MDScreen, ThemableBehavior):
    """MDScreen that exposes a chrome-aware inner content area.

    Class attributes (override on subclasses):
        adjust_title_bar     : bool, default True
        adjust_app_bar       : bool, default True
        adjust_bottom_appbar : bool, default True

    The screen itself stays at `(1, 1)` so screen-manager transitions
    animate uniformly. Subclasses generally add widgets via the normal
    `add_widget`; they're routed into the content area. Use
    `add_overlay` for widgets that need to sit at the window edge
    (e.g. a `BottomAppBar`).
    """

    adjust_title_bar = True
    adjust_app_bar = True
    adjust_bottom_appbar = True

    content = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 1)
        self.pos_hint = {"center_x": 0.5, "center_y": 0.5}

        self.content = _InnerContent()
        # Propagate subclass overrides into the inner layout before the
        # height computation runs.
        self.content.adjust_title_bar = self.adjust_title_bar
        self.content.adjust_app_bar = self.adjust_app_bar
        self.content.adjust_bottom_appbar = self.adjust_bottom_appbar
        self.content._update_adjusted_height()
        if self.adjust_bottom_appbar:
            self.content.y = 82
        MDScreen.add_widget(self, self.content)

    # ----- widget management ----------------------------------------------

    def add_widget(self, widget, *args, **kwargs):
        """Add to the chrome-aware content area by default.

        Use `add_overlay` for widgets that should sit at the window edge
        (e.g. a `BottomAppBar`, snackbars).
        """
        if self.content is None or widget is self.content:
            return MDScreen.add_widget(self, widget, *args, **kwargs)
        return self.content.add_widget(widget, *args, **kwargs)

    def add_overlay(self, widget, *args, **kwargs):
        """Bypass the inner content area and add directly to the screen.

        Use for widgets that own their own positioning, e.g. a
        `BottomAppBar` that anchors to the bottom of the window.
        """
        return MDScreen.add_widget(self, widget, *args, **kwargs)
