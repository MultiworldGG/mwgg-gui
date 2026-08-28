"""
Live YAML preview pane.

Wraps `kivy.uix.codeinput.CodeInput` with a Pygments `YamlLexer`. Exposes:

  - `set_text(text)` - set the preview without re-firing on_text
  - `get_text()`     - read current text
  - `dirty`          - True once the user hand-edits the text (programmatic
    `set_text` writes don't count); the screen consults it before pushing
  - a `[Sync ⇒ Form]` button that calls back to the screen with the parsed
    form state, or shows a parse-error strip beneath the toolbar if the
    text doesn't round-trip
  - a `[Resync]` button, hidden until `show_sync_paused()`, that calls
    `on_resync` - the screen's resume-live-sync affordance.

Kivy markup is BBCode under the hood; CodeInput's `BBCodeFormatter` emits
exactly what the rest of the Kivy label renderer expects, so we don't need
to bridge between formats.
"""
from __future__ import annotations

import logging

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.codeinput import CodeInput
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.label import MDLabel

from pygments.lexers.data import YamlLexer

from .yaml_io import ParseError, yaml_to_form_state

logger = logging.getLogger("Client")

__all__ = ("YamlPreview",)


Builder.load_string(
    """
<YamlPreview>:
    orientation: 'vertical'
    spacing: dp(4)
    padding: dp(6)

    MDBoxLayout:
        id: toolbar
        orientation: 'horizontal'
        size_hint_y: None
        height: dp(40)
        spacing: dp(6)
        MDLabel:
            text: "Generated YAML"
            theme_text_color: "Primary"
            bold: True
        MDButton:
            id: resync_btn
            style: "tonal"
            on_release: root.resync()
            MDButtonIcon:
                icon: "refresh"
            MDButtonText:
                text: "Resync"
        MDButton:
            style: "tonal"
            on_release: root.sync_to_form()
            MDButtonIcon:
                icon: "swap-horizontal"
            MDButtonText:
                text: "Sync → Form"

    MDLabel:
        id: error_strip
        text: ""
        size_hint_y: None
        height: dp(0)
        theme_text_color: "Custom"
        text_color: app.theme_cls.errorColor
        opacity: 0
    """
)


class YamlPreview(MDBoxLayout):
    """The right-hand pane: a CodeInput holding the live YAML preview."""

    game_name = StringProperty("")
    on_sync = ObjectProperty(None)
    """Callback signature: `on_sync(parsed_form_state)`; invoked when the
    user clicks Sync and the YAML parses cleanly."""
    known_options = ObjectProperty(None)
    """Optional zero-arg callable returning the option names the form owns
    (or None). Game-section keys outside it are preserved as extras rather
    than parsed as options; see `yaml_io.yaml_to_form_state`."""
    on_resync = ObjectProperty(None)
    """Zero-arg callback fired by the Resync button while sync is paused."""
    dirty = BooleanProperty(False)
    """True once the user hand-edits the text; `set_text` never sets it."""

    def __init__(self, game_name: str, on_sync=None, known_options=None,
                 on_resync=None, **kwargs):
        super().__init__(**kwargs)
        self.game_name = game_name
        self.on_sync = on_sync
        self.known_options = known_options
        self.on_resync = on_resync
        self._suppress_on_text = False

        # Detached, not ghosted: opacity-0 still reserves toolbar width.
        # `.__self__` unwraps the ids WeakProxy; while detached this is
        # the button's only strong reference.
        self._resync_btn = self.ids.resync_btn.__self__
        self.ids.toolbar.remove_widget(self._resync_btn)

        self._code = CodeInput(
            text="",
            lexer=YamlLexer(),
            size_hint=(1, 1),
        )
        self._code.bind(text=self._on_user_edit)
        self.add_widget(self._code)

    # -- public API --------------------------------------------------------

    def set_text(self, text: str):
        """Replace the YAML text without echoing the change back to the
        form. Use when the form has changed and is pushing into the view.

        Restores cursor and scroll afterwards: TextInput assignment moves
        the cursor to the end, yanking the pane to the bottom on every
        push."""
        code = self._code
        if text == code.text:
            return
        cursor, scroll_x, scroll_y = code.cursor, code.scroll_x, code.scroll_y
        self._suppress_on_text = True
        try:
            code.text = text
        finally:
            self._suppress_on_text = False
        row = min(cursor[1], len(code._lines) - 1)
        code.cursor = (min(cursor[0], len(code._lines[row])), row)

        def _restore(_dt):
            # TextInput's queued layout refresh scrolls to the cursor and would overwrite a same-frame restore.
            code.scroll_x = scroll_x
            code.scroll_y = min(scroll_y, max(0, code.minimum_height - code.height))

        Clock.schedule_once(_restore, 0)

    def get_text(self) -> str:
        return self._code.text

    def _on_user_edit(self, _instance, _text):
        if not self._suppress_on_text:
            self.dirty = True

    def sync_to_form(self):
        """Parse the current text. On success, invoke `on_sync` with the
        parsed form state. On failure, show the error strip.

        Does NOT clear `dirty`: a clean parse doesn't mean a lossless
        round-trip. The caller re-renders the canonical YAML after
        applying and clears `dirty` only on a verbatim match."""
        try:
            known = self.known_options() if self.known_options else None
            state = yaml_to_form_state(
                self._code.text, self.game_name, known_options=known
            )
        except ParseError as e:
            self._show_error(str(e))
            return
        self._hide_error()
        if self.on_sync:
            self.on_sync(state)

    def resync(self):
        if self.on_resync:
            self.on_resync()

    def show_sync_paused(self):
        if self._resync_btn.parent is None:
            # children are reverse-ordered: index 1 lands between title and Sync button.
            self.ids.toolbar.add_widget(self._resync_btn, index=1)

    def hide_sync_paused(self):
        if self._resync_btn.parent is not None:
            self.ids.toolbar.remove_widget(self._resync_btn)

    # -- error strip -------------------------------------------------------

    def _show_error(self, message: str):
        strip = self.ids.error_strip
        strip.text = f"⚠ {message}"
        strip.opacity = 1
        strip.height = dp(28)

    def _hide_error(self):
        strip = self.ids.error_strip
        strip.text = ""
        strip.opacity = 0
        strip.height = dp(0)
