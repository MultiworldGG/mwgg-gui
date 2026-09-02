from __future__ import annotations
"""
Item-hover progression tooltip for the console.

ConsoleToolTip - MDTooltipPlain styled like the <ListItemTooltip> kv rule
(overrides/expansionlist.kv) but managed manually on Window: kivymd's
MDTooltip behavior anchors to the host widget's center, which is wrong for
a console-wide host, so it is positioned at mouse + dp(12) and clamped to
the window edges instead (clamp arithmetic borrowed from
MDTooltip.adjust_tooltip_position, reveal animation from
MDTooltip.animation_tooltip_show; dismiss is immediate so scrolled or
clicked-away tooltips never linger over stale text).

ConsoleHoverBehavior - plain-object mixin for TextConsole (same MRO-safe
pattern as kvui's HoverBehavior). Maps Window.mouse_pos -> to_widget ->
get_cursor_from_xy -> _map_cursor_to_markup_position -> absolute markup
index -> NetUtils.find_enclosing_color_span -> item-class color hex ->
ITEM_CLASS_TOOLTIP_LABELS label. The NetUtils helpers are feature-detected
via getattr, so a version-skewed core simply disables the feature.
"""
import NetUtils

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.tooltip import MDTooltipPlain
from mwgg_gui.overrides.hoverlabel import SimpleHoverLabel

__all__ = ('ConsoleToolTip', 'ConsoleHoverBehavior',)


class ConsoleToolTip(MDTooltipPlain):
    """Plain tooltip shown next to the mouse cursor over the console."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_text_color = "Custom"
        self.theme_bg_color = "Custom"
        self.refresh_colors()

    def refresh_colors(self):
        """Re-read theme colors; called at each show so a mid-session theme
        switch is honored."""
        self.md_bg_color = self.theme_cls.secondaryContainerColor
        self.text_color = self.theme_cls.onSecondaryContainerColor

#TODO: This is SO VERY WRONG. Anyway we need to use the SimpleHoverLabel and shove it in the console text instead.
class ConsoleHoverBehavior:
    """Hover hit-testing + tooltip lifecycle for the console text field.

    Plain-object mixin, listed FIRST in the host's bases so its
    on_touch_down runs before the text field's selection handling. It never
    overrides selection or scroll handlers, and its Window bindings are
    managed exclusively through start/stop_hover_tracking (screen
    enter/leave plus the init_important re-arm) -- never in __init__, so
    they cannot outlive screen visibility.
    """

    #: seconds the mouse must rest before the (heavier) hit-test runs
    HOVER_HITTEST_DELAY = 0.15

    _hover_bound = False
    _hover_trigger = None
    _hover_tooltip = None
    _hover_last_pos = None
    _hover_span = None

    def start_hover_tracking(self):
        """Bind hover tracking. Idempotent: on_enter fires once at startup
        before the deferred init_important builds the console, so this is
        called again from init_important and on every later screen entry."""
        if self._hover_bound:
            return
        self._hover_bound = True
        if self._hover_trigger is None:
            self._hover_trigger = Clock.create_trigger(
                self._hover_hittest, self.HOVER_HITTEST_DELAY)
        Window.fbind('mouse_pos', self._on_hover_mouse_pos)
        Window.fbind('on_cursor_leave', self._dismiss_hover_tooltip)
        # Any scroll (wheel, drag, or auto-scroll-on-append) invalidates the hit.
        self.fbind('scroll_y', self._dismiss_hover_tooltip)

    def stop_hover_tracking(self):
        if not self._hover_bound:
            return
        self._hover_bound = False
        Window.funbind('mouse_pos', self._on_hover_mouse_pos)
        Window.funbind('on_cursor_leave', self._dismiss_hover_tooltip)
        self.funbind('scroll_y', self._dismiss_hover_tooltip)
        self._hover_trigger.cancel()
        self._dismiss_hover_tooltip()

    def on_touch_down(self, touch):
        self._dismiss_hover_tooltip()
        return super().on_touch_down(touch)

    def _on_hover_mouse_pos(self, window, pos):
        if not self.get_root_window():
            return
        self._hover_last_pos = pos
        tip = self._hover_tooltip
        if tip is not None and tip.parent is not None \
                and not self._hover_pos_in_span(pos):
            self._dismiss_hover_tooltip()
        # Pending Kivy triggers do NOT restart on call -- cancel first so
        # the hit-test runs once the mouse rests, not mid-motion.
        self._hover_trigger.cancel()
        self._hover_trigger()

    def _hover_hittest(self, *args):
        pos = self._hover_last_pos
        if pos is None or not self._hover_bound:
            return
        # Suppress hover while a touch / selection drag is active.
        if getattr(self, '_touch_count', 0) or getattr(self, '_selection_touch', None):
            return
        if not self._hover_tooltips_enabled():
            self._dismiss_hover_tooltip()
            return
        # Feature-detect the core-side helper (absent on old cores).
        find_span = getattr(NetUtils, 'find_enclosing_color_span', None)
        if find_span is None:
            return
        local = self.to_widget(*pos)
        if not self.collide_point(*local) or self._hover_beyond_text(*local):
            self._dismiss_hover_tooltip()
            return
        index = self._map_cursor_to_markup_position(self.get_cursor_from_xy(*local))
        span = find_span(self.text, index)
        if span is None:
            self._dismiss_hover_tooltip()
            return
        start, end, color_hex = span
        if color_hex.lower() == (self.text_default_color or "").lower():
            self._dismiss_hover_tooltip()
            return
        label = self._label_for_hex(color_hex)
        if label is None:
            self._dismiss_hover_tooltip()
            return
        self._show_hover_tooltip(label, pos)
        self._hover_span = (start, end)

    def _show_hover_tooltip(self, text, pos):
        tip = self._hover_tooltip
        if tip is None:
            tip = self._hover_tooltip = ConsoleToolTip()
        if tip.parent is not None:
            if tip.text == text:
                return  # same label: stay anchored where the mouse rested
            self._dismiss_hover_tooltip()
        tip.refresh_colors()
        tip.text = text
        # Force the texture now so adaptive sizing yields the final size
        # before clamping (the tooltip was just retexted).
        tip.texture_update()
        x = pos[0] + dp(12)
        y = pos[1] + dp(12)
        if x + tip.width > Window.width:
            x = Window.width - (tip.width + dp(10))
        elif x < 0:
            x = dp(10)
        if y + tip.height > Window.height:
            y = Window.height - (tip.height + dp(10))
        elif y < 0:
            y = dp(10)
        tip.pos = (x, y)
        Window.add_widget(tip)
        Animation.cancel_all(tip)
        (Animation(scale_value_x=1, scale_value_y=1, d=0.2)
         + Animation(opacity=1, d=0.2)).start(tip)

    def _dismiss_hover_tooltip(self, *args):
        self._hover_span = None
        tip = self._hover_tooltip
        if tip is None:
            return
        Animation.cancel_all(tip)
        if tip.parent is not None:
            Window.remove_widget(tip)
        tip.opacity = 0
        tip.scale_value_x = tip.scale_value_y = 0

    def _label_for_hex(self, color_hex):
        """Reverse-lookup the emitted hex against the parser's color snapshot,
        allowlisted to the item-class colors. Returns None for non-item hexes
        (command echo, players, locations, hint statuses, ...)."""
        labels = getattr(NetUtils, 'ITEM_CLASS_TOOLTIP_LABELS', None)
        if not labels:
            return None  # version-skewed core: feature disabled
        parser = getattr(NetUtils, 'KivyMarkupJSONtoTextParser', None)
        # The ClassVar is populated lazily by the first parser construction,
        # and log-record text can be hovered before any print_json.
        codes = getattr(parser, 'color_codes', None) or {}
        color_hex = color_hex.lower()
        for name, label in labels.items():
            code = codes.get(name)
            if code and code.lstrip('#').lower() == color_hex:
                return label
        return None

    def _hover_pos_in_span(self, pos):
        """True while the (window-space) mouse pos still maps inside the span
        the visible tooltip was shown for."""
        span = self._hover_span
        if span is None:
            return False
        local = self.to_widget(*pos)
        if not self.collide_point(*local) or self._hover_beyond_text(*local):
            return False
        index = self._map_cursor_to_markup_position(self.get_cursor_from_xy(*local))
        return span[0] <= index < span[1]

    def _hover_beyond_text(self, x, y):
        """get_cursor_from_xy clamps row and col into range, so blank space
        below the last line (or right of a line's end) would otherwise map to
        a valid index. Recompute the unclamped row / x extent and bail."""
        lines = self._lines
        if not lines:
            return True
        dy = self.line_height + self.line_spacing
        if dy <= 0:
            return True
        scroll_y = self.scroll_y if self.scroll_y > 0 else 0
        row = int(round(((self.top - self.padding[1] + scroll_y) - y) / dy - 0.5))
        if row < 0 or row >= len(lines):
            return True
        # Markup tags measure zero width via the markup-aware
        # _get_text_width, so this is the row's visible text extent.
        row_width = self._get_text_width(lines[row], self.tab_width, self._label_cached)
        return (x - self.x) + self.scroll_x > self.padding[0] + row_width

    def _hover_tooltips_enabled(self):
        app = getattr(self, 'app', None) or MDApp.get_running_app()
        if app is None:
            return True
        return app.app_config.getboolean('client', 'item_tooltips', fallback=True)
