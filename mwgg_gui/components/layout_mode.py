"""App-wide layout mode: size classes, input mode, and window chrome metrics.

One shared LayoutMode instance (exposed as ``app.layout_mode``) is the single
source of truth for:

* Material-3 window size classes (``width_class``/``height_class``:
  compact < 600dp, medium 600-839dp, expanded >= 840dp) and ``orientation``,
  recomputed on window resize. The desktop shell clamps ``width_class`` to
  medium-or-wider, so existing desktop layouts provably never enter the
  compact paths. ``MWGG_FORCE_LAYOUT=compact|medium|expanded`` overrides the
  classification for dev testing.
* ``touch_mode`` — true on Android/iOS, drives hover-vs-tap affordances.
* Chrome metrics — the heights the fixed bars remove from a screen's usable
  area. Historically these were literals scattered across screens (43/60/82dp,
  raw 185/103/82/39px); every consumer now reads them from here. On win32 the
  values match the historical ones exactly; elsewhere the titlebar metrics are
  zero because app.build() never adds the Titlebar widget off-Windows (the old
  literals subtracted it anyway — a latent layout bug).
* ``safe_inset_top``/``safe_inset_bottom`` — notch/home-bar insets, folded
  into the chrome alias properties. Zero until populated by the mobile shell.
"""
import os
import sys

from kivy.core.window import Window
from kivy.event import EventDispatcher
from kivy.metrics import dp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    NumericProperty,
    OptionProperty,
)
from mwgg_gui import bootstrap
from mwgg_gui.constants import IS_MOBILE

_SIZE_CLASSES = ("compact", "medium", "expanded")

_FORCE_ENV = "MWGG_FORCE_LAYOUT"


def _classify(extent_dp: float) -> str:
    if extent_dp < 600:
        return "compact"
    if extent_dp < 840:
        return "medium"
    return "expanded"


class LayoutMode(EventDispatcher):
    width_class = OptionProperty("expanded", options=list(_SIZE_CLASSES))
    height_class = OptionProperty("medium", options=list(_SIZE_CLASSES))
    orientation = OptionProperty("landscape", options=["portrait", "landscape"])

    touch_mode = BooleanProperty(IS_MOBILE)
    # Matches the Titlebar gate in MultiMDApp.build(): the custom titlebar
    # widget only exists on Windows desktop.
    has_titlebar = BooleanProperty(False)

    chrome_titlebar = NumericProperty(0)
    # Top padding TopAppBarLayout uses to clear the titlebar. Historically a
    # raw 39 (not dp, intentionally — the win32 window is DPI-unaware).
    chrome_titlebar_pad = NumericProperty(0)
    chrome_top_appbar = NumericProperty(dp(60))
    chrome_bottom_appbar = NumericProperty(dp(82))

    safe_inset_top = NumericProperty(0)
    safe_inset_bottom = NumericProperty(0)

    def _get_chrome_top_total(self):
        return self.chrome_titlebar + self.chrome_top_appbar + self.safe_inset_top

    chrome_top_total = AliasProperty(
        _get_chrome_top_total,
        bind=("chrome_titlebar", "chrome_top_appbar", "safe_inset_top"),
        cache=True,
    )

    def _get_chrome_bottom_total(self):
        return self.chrome_bottom_appbar + self.safe_inset_bottom

    chrome_bottom_total = AliasProperty(
        _get_chrome_bottom_total,
        bind=("chrome_bottom_appbar", "safe_inset_bottom"),
        cache=True,
    )

    def _get_chrome_total(self):
        return self._get_chrome_top_total() + self._get_chrome_bottom_total()

    chrome_total = AliasProperty(
        _get_chrome_total,
        bind=("chrome_top_total", "chrome_bottom_total"),
        cache=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._min_width_class = "compact" if bootstrap.is_mobile_shell() else "medium"
        self._forced_class = os.environ.get(_FORCE_ENV) or None
        if self._forced_class not in _SIZE_CLASSES:
            self._forced_class = None
        if bootstrap.is_desktop_shell() and sys.platform == "win32":
            self.has_titlebar = True
            self.chrome_titlebar = dp(43)
            self.chrome_titlebar_pad = 39
        Window.bind(size=self._on_window_size)
        self._on_window_size(Window, Window.size)

    def force_width_class(self, width_class: str | None) -> None:
        """Pin both size classes to `width_class` (None returns to
        window-size classification). Used by the settings Compact Mode
        switch and the MWGG_FORCE_LAYOUT env override."""
        self._forced_class = width_class if width_class in _SIZE_CLASSES else None
        self._on_window_size(Window, Window.size)

    def _on_window_size(self, _window, size):
        width, height = size
        self.orientation = "portrait" if height > width else "landscape"
        if self._forced_class is not None:
            self.width_class = self._forced_class
            self.height_class = self._forced_class
            return
        # px -> dp: dp(1) is the device's density factor.
        width_class = _classify(width / dp(1))
        height_class = _classify(height / dp(1))
        if _SIZE_CLASSES.index(width_class) < _SIZE_CLASSES.index(self._min_width_class):
            width_class = self._min_width_class
        self.width_class = width_class
        self.height_class = height_class


_instance: LayoutMode | None = None


def get_layout_mode() -> LayoutMode:
    """Shared instance; created on first use, owned by the running app
    (assigned to ``app.layout_mode`` in MultiMDApp.__init__)."""
    global _instance
    if _instance is None:
        _instance = LayoutMode()
    return _instance
