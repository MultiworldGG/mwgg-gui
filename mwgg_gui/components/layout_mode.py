"""
Compact-mode layout service, exposed as ``app.layout_mode``.

Compact Mode is the Settings > Interface > Layout switch: a portrait window
whose screens stack their panes vertically. The launcher rebuilds itself when
the switch flips; clients are separate processes and read the persisted
value at boot. The pure helpers stay Kivy-free so the unit tests can load
this module with the Kivy imports stubbed.
"""
from __future__ import annotations

__all__ = ("LayoutMode", "get_layout_mode", "read_compact_mode", "window_geometry")

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.event import EventDispatcher
from kivy.metrics import dp
from kivy.properties import AliasProperty, BooleanProperty, NumericProperty

# (size, minimum size) per mode. The desktop values match the historical
# post-splash resize and the graphics config minimums.
_WINDOW_GEOMETRY = {
    False: ((1100, 700), (600, 700)),
    True: ((460, 800), (400, 640)),
}


def read_compact_mode(app_config) -> bool:
    """client.compact_mode; a client.ini written by the old switch only
    carries device_orientation=Portrait, which meant the same thing."""
    if app_config.has_option("client", "compact_mode"):
        return app_config.getboolean("client", "compact_mode")
    return app_config.get("client", "device_orientation", fallback="") == "Portrait"


def window_geometry(compact: bool) -> tuple[tuple[int, int], tuple[int, int]]:
    """(window size, minimum window size) for the mode."""
    return _WINDOW_GEOMETRY[bool(compact)]


class LayoutMode(EventDispatcher):
    compact = BooleanProperty(False)
    # Height the bottom bar's permanently docked text input adds above the
    # bar in compact mode (dp(56) field plus margins); 0 otherwise.
    docked_input_height = NumericProperty(dp(72))

    def _get_docked_input(self):
        return self.docked_input_height if self.compact else 0

    docked_input = AliasProperty(
        _get_docked_input, bind=("compact", "docked_input_height"), cache=True)

    def apply_window_geometry(self) -> None:
        size, minimum = window_geometry(self.compact)
        Window.size = size
        Window.minimum_width, Window.minimum_height = minimum
        # On win32 Window.width/height read the GL surface, which SDL resizes
        # only after the property observers already ran, so kv bindings such
        # as `Window.height-103` keep the old value; re-dispatch next frame.
        Clock.schedule_once(lambda dt: Window.property("_size").dispatch(Window), 0)


_instance: LayoutMode | None = None


def get_layout_mode() -> LayoutMode:
    """Shared instance, created on first use; every MultiMDApp instance
    (phantom post-takeover ones included) binds to this one object."""
    global _instance
    if _instance is None:
        _instance = LayoutMode()
    return _instance
