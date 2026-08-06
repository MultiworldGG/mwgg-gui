"""
Live YAML preview pane.

Wraps `kivy.uix.codeinput.CodeInput` with a Pygments `YamlLexer`. Exposes:

  - `set_text(text)` — set the preview without re-firing on_text
  - `get_text()`     — read current text
  - a `[Sync ⇒ Form]` button that calls back to the screen with the parsed
    form state, or shows a parse-error strip beneath the toolbar if the
    text doesn't round-trip.

Kivy markup is BBCode under the hood; CodeInput's `BBCodeFormatter` emits
exactly what the rest of the Kivy label renderer expects, so we don't need
to bridge between formats.
"""
from __future__ import annotations

import logging

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
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
    """Callback signature: `on_sync(parsed_form_state)` — invoked when the
    user clicks Sync and the YAML parses cleanly."""
    known_options = ObjectProperty(None)
    """Optional zero-arg callable returning the option names the form owns
    (or None). Game-section keys outside it are preserved as extras rather
    than parsed as options — see `yaml_io.yaml_to_form_state`."""

    def __init__(self, game_name: str, on_sync=None, known_options=None, **kwargs):
        super().__init__(**kwargs)
        self.game_name = game_name
        self.on_sync = on_sync
        self.known_options = known_options
        self._suppress_on_text = False

        self._code = CodeInput(
            text="",
            lexer=YamlLexer(),
            size_hint=(1, 1),
        )
        self.add_widget(self._code)

    # -- public API --------------------------------------------------------

    def set_text(self, text: str):
        """Replace the YAML text without echoing the change back to the
        form. Use when the form has changed and is pushing into the view."""
        if text == self._code.text:
            return
        self._suppress_on_text = True
        try:
            self._code.text = text
        finally:
            self._suppress_on_text = False

    def get_text(self) -> str:
        return self._code.text

    def sync_to_form(self):
        """Parse the current text. On success, invoke `on_sync` with the
        parsed form state. On failure, show the error strip."""
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
