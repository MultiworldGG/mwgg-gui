"""
InnerMDScreen — MDScreen with a chrome-aware inner content area.

The app's root layout layers the title bar and top app bar over the
screen manager, and screens typically own their own bottom app bar. A
bare `MDScreen` fills the entire window so anything added to it
overlaps the chrome.

The fix can't go on the screen itself: the `MDScreenManager` uses
`SwapTransition` (and friends) to animate between screens, and those
transitions look uniform only when every screen is the same full-window
size — a smaller screen would leak chrome through the slide. So we
keep the screen at `(1, 1)` and route widgets into an inner content
layout that's positioned for the chrome.

`InnerMDScreen` builds that inner layout once and proxies the normal
`add_widget` call into it, so subclasses use the screen exactly like
they would a bare `MDScreen`:

    class MyScreen(InnerMDScreen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_widget(my_content)        # inside the chrome
            self.add_overlay(my_bottom_bar)    # full-screen edge

The inner layout uses the existing `AutoAdjustHeightBehavior` mixin
from `mwgg_gui.components.mw_theme`, so resize behavior matches every
other screen in the app.

Set the class attribute `adjust_bottom_appbar = False` if your screen
does not own a bottom app bar (settings pattern).

NOTE: this module is intentionally *not* re-exported from
`overrides/__init__.py` — `mw_theme.py` imports from `overrides`
during its own initialization, and pulling `AutoAdjustHeightBehavior`
from `mw_theme` here would deadlock the cycle. Import the class
directly:

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
    `add_widget` — they're routed into the content area. Use
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
