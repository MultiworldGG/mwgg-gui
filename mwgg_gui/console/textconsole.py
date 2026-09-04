from __future__ import annotations
"""
TextConsole class - creates the text console to be added to the following screens:
console
console_compact

This is a wrapper around the updated MarkupTextField class, and is used to
display the text console.
"""
from dataclasses import dataclass
from typing import Callable, Optional
from kivy.core.window import Window
from kivymd.uix.floatlayout import MDFloatLayout
from kivy.properties import ObjectProperty
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.button import MDFabButton
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
import logging
from logging.handlers import QueueHandler
from multiprocessing import Queue
from multiprocessing.queues import Empty
from kivy.utils import get_hex_from_color
from mwgg_gui.overrides.markuptextfield import MarkupTextField
from mwgg_gui.components.guidataclasses import MarkupPair

from NetUtils import TEXT_COLORS

__all__ = ('TextConsole', 'ConsoleView', 'ConsolePair')

Builder.load_string('''
<BottomScrollButton>:
    id: bottom_scroll_button
    icon: 'arrow-down-bold-outline'
    style: 'small'
''')

class BottomScrollButton(MDFabButton):
    pass

## helper class to return both Client and Archipelago logs
class ConsoleFilter(logging.Filter):
    def filter(self, record):
        if record.name.endswith("Client"):
            return True
        elif record.name == "Archipelago" or record.name == "MultiWorld":
            return True
        return False


@dataclass
class ConsolePair(MarkupPair):
    """Console line plus the flag the Admin screen's mirror drops on: item
    sends, cheats, and hints all carry an item node."""
    item_traffic: bool = False


class TextConsole(MarkupTextField, ThemableBehavior):
    text_buffer: Queue
    app: MDApp
    # Mirrors drop the queue items this returns False for.
    line_filter: Optional[Callable[[object], bool]]

    def __init__(self, bottom_scroll_button=None, pull_buffer: bool = True,
                 line_filter: Optional[Callable[[object], bool]] = None, **kwargs):
        super().__init__(bottom_scroll_button=bottom_scroll_button, **kwargs)
        self.app = MDApp.get_running_app()
        self.line_filter = line_filter
        # Secondary consoles (the Admin screen) receive every item this one
        # drains, through their own line_filter; only one console may consume
        # app.text_buffer.
        self.mirrors: list[TextConsole] = []
        self.allow_hover = self.app.app_config.getboolean('client', 'item_tooltips', fallback=True)
        self.font_name = self.theme_cls.font_styles.Monospace['small']['font-name']
        self.font_size = self.theme_cls.font_styles.Monospace['small']['font-size']
        self.line_spacing = self.theme_cls.font_styles.Monospace['small']['line-height']
        self.selection_color = self.theme_cls.secondaryColor
        self.selection_color[3] = 0.3
        self.text_default_color = self.app.theme_mw.markup_tags_theme.default_color[0 if self.app.theme_mw.theme_style == "Light" else 1]
        self.multiline = True
        self.do_wrap = True
        self.auto_indent = True
        self.use_menu = True
        self.readonly = True
        self.cursor_color = self.theme_cls.primaryColor
        self.text_buffer = self.app.text_buffer
        Clock.schedule_once(self.set_all_players_chat, 0)
        # self.lines_to_scroll = int(self.app.config.get('client', 'scroll_lines', fallback=3))

        if pull_buffer:
            Clock.schedule_interval(self.add_text_from_buffer, 0)

    def set_all_players_chat(self, dt):
        self.app.ctx.all_players_chat = self.app.app_config.getboolean('client', 'all_players_chat', fallback=True)

    @staticmethod
    def _texts_for(queue_item) -> tuple[str, str]:
        """(markup, plaintext) for a MarkupPair, a plain string, or a log record."""
        if isinstance(queue_item, MarkupPair):
            return queue_item.text, queue_item.plaintext
        if isinstance(queue_item, str):
            return queue_item, queue_item
        if hasattr(queue_item, 'msg'):
            return queue_item.msg, queue_item.msg
        raise ValueError(f"Invalid queue item type: {type(queue_item)}")

    def append_items(self, items: list) -> None:
        """Append the queue items this console's line_filter accepts, as one
        set_texts call."""
        accepted = [item for item in items if self.line_filter is None or self.line_filter(item)]
        if not accepted:
            return
        texts = [self._texts_for(item) for item in accepted]
        self.set_texts("\n".join(markup for markup, _ in texts),
                       "\n".join(plaintext for _, plaintext in texts))

    def add_text_from_buffer(self, dt):
        chunk_size = 50  # Process up to 50 items per frame
        items = []
        try:
            for _ in range(chunk_size):
                items.append(self.text_buffer.get_nowait())
        except Empty:
            pass
        if not items:
            return
        try:
            self.append_items(items)
            for mirror in self.mirrors:
                mirror.append_items(items)
        except Exception as e:
            print(e)

class ConsoleView(MDFloatLayout):
    text_console = ObjectProperty(None)
    bottom_scroll_button = ObjectProperty(None)

    def __init__(self, mirror_of: TextConsole | None = None,
                 line_filter: Optional[Callable[[object], bool]] = None, **kwargs):
        super().__init__(**kwargs)
        self.bottom_scroll_button = BottomScrollButton(opacity=0, x=Window.width - dp(60), y=dp(10))
        self.text_console = TextConsole(bottom_scroll_button=self.bottom_scroll_button, pos_hint={"x": 0, "y": 0},
                                        size_hint=(1-(4/Window.width),1-(185/Window.height)),
                                        pull_buffer=mirror_of is None, line_filter=line_filter)
        if mirror_of is not None:
            mirror_of.mirrors.append(self.text_console)
        self.add_widget(self.text_console)
        self.text_console.fbind('scroll_y', self.set_bottom_scroll_button_opacity)
        self.add_widget(self.bottom_scroll_button)

    def console_handler(self) -> QueueHandler:
        """Create a StreamHandler that writes directly to the text_buffer"""
        _console_out = QueueHandler(queue=self.text_console.text_buffer)
        _console_out.setFormatter(logging.Formatter("%(message)s"))
        _console_out.setLevel(logging.INFO)
        _console_out.addFilter(ConsoleFilter())
        return _console_out

    def set_bottom_scroll_button_opacity(self, instance, value):
        """Show button when not at the bottom of the scroll"""
        max_scroll_y = max(0, self.text_console.minimum_height - self.text_console.height)
        # Show button if scroll_y is less than max_scroll_y (not at bottom)
        # Add small threshold to avoid flickering at the exact bottom
        self.bottom_scroll_button.opacity = 1 if value < max_scroll_y - self.text_console.height else 0
