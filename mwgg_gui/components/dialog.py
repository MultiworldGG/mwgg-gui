"""
Dialog class - MessageBox override for dialogs
"""
from __future__ import annotations
__all__ = ("MessageBox", "CodeWarningBox", "ConsoleBox", "confirm_arbitrary_code")

import logging

from kivymd.uix.dialog import (MDDialog,
                               MDDialogHeadlineText,
                               MDDialogSupportingText,
                               MDDialogButtonContainer,
                               MDDialogContentContainer)
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField, MDTextFieldHelperText
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.app import MDApp
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivy.properties import ObjectProperty

from typing import Callable
from asyncio import Queue

logger = logging.getLogger("Client")

class MessageBox(MDDialog):
    """
    A simple KivyMD dialog class that can be used throughout the codebase.
    
    Args:
        title (str): The dialog title
        message (str): The dialog message content
        is_error (bool): If True, shows error styling
    """

    cancel_button: ObjectProperty

    def __init__(self, title="", message="", callback: Callable[[bool], None] = None, is_error=False,
                 ok_text="OK", cancel_text="Cancel"):
        super().__init__()
        self.title = title
        self.message = message
        self.callback = callback
        self.is_error = is_error
        self.ok_text = ok_text
        self.app = MDApp.get_running_app()
        self.dialog = None
        self.cancel_button = Widget()
        if self.callback:
            self.cancel_button = MDButton(
                MDButtonText(
                    text=cancel_text,
                    theme_text_color="Custom",
                    text_color=self.app.theme_cls.onSurfaceColor,
                ),
                on_release=self._cancel,
            )

    def _ok(self, instance):
        self.dialog.dismiss()
        self.dialog = None
        if self.callback:
            self.callback(True)
    
    def _cancel(self, instance):
        self.dialog.dismiss()
        self.dialog = None
        if self.callback:
            self.callback(False)
        
    def open(self):
        """Opens the dialog and displays it to the user."""
        self.dialog = MDDialog(
            MDDialogHeadlineText(
                text=self.title,
            ),
            MDDialogContentContainer(
                MDDialogSupportingText(
                    text=self.message,
                    theme_text_color="Custom" if self.is_error else "Primary",
                    text_color=self.app.theme_cls.errorColor if self.is_error else self.app.theme_cls.onSurfaceColor,
                ),
            ),
            MDDialogButtonContainer(
                self.cancel_button,
                MDButton(
                    MDButtonText(
                        text=self.ok_text,
                        theme_text_color="Custom",
                        text_color=self.app.theme_cls.errorColor if self.is_error else self.app.theme_cls.onSurfaceColor,
                    ),
                    on_release=lambda instance: self._ok(instance),
                ),
                spacing=dp(8),
            ),
        )
        self.dialog.state_press = 0
        self.dialog.open()


class CodeWarningBox(MessageBox):
    """
    Arbitrary-code warning dialog: a MessageBox with a "Don't warn me again"
    checkbox row and a configurable confirm-button label. When confirmed with
    the checkbox active, the given `[security]` config key is persisted so
    `confirm_arbitrary_code` skips the dialog on later calls.

    Args:
        title (str): The dialog title
        message (str): The warning text
        callback (Callable[[bool], None]): Confirm/cancel result callback
        confirm_text (str): Label for the confirm button
        suppress_config_key (str): `[security]` key persisted on confirmed+checked
    """

    def __init__(self, title="", message="", callback: Callable[[bool], None] = None,
                 confirm_text="Continue", suppress_config_key=""):
        super().__init__(title=title, message=message, callback=callback)
        self.confirm_text = confirm_text
        self.suppress_config_key = suppress_config_key
        self.suppress_checkbox = None

    def _ok(self, instance):
        if self.suppress_config_key and self.suppress_checkbox and self.suppress_checkbox.active:
            try:
                self.app.app_config.adddefaultsection('security')
                self.app.app_config.set('security', self.suppress_config_key, 'True')
                self.app.app_config.write()
            except Exception as e:
                logger.error(f"Failed to persist warning suppression: {e}", exc_info=True)
        super()._ok(instance)

    def open(self):
        """Opens the dialog and displays it to the user."""
        self.suppress_checkbox = MDCheckbox(
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
        )
        self.dialog = MDDialog(
            MDDialogHeadlineText(
                text=self.title,
            ),
            MDDialogContentContainer(
                MDDialogSupportingText(
                    text=self.message,
                    theme_text_color="Primary",
                    text_color=self.app.theme_cls.onSurfaceColor,
                ),
                MDBoxLayout(
                    self.suppress_checkbox,
                    MDLabel(
                        text="Don't warn me again",
                        theme_text_color="Custom",
                        text_color=self.app.theme_cls.onSurfaceColor,
                        valign="center",
                        pos_hint={"center_y": 0.5},
                    ),
                    orientation="horizontal",
                    spacing=dp(8),
                    size_hint_y=None,
                    height=dp(40),
                ),
                orientation="vertical",
                spacing=dp(8),
            ),
            MDDialogButtonContainer(
                self.cancel_button,
                MDButton(
                    MDButtonText(
                        text=self.confirm_text,
                        theme_text_color="Custom",
                        text_color=self.app.theme_cls.onSurfaceColor,
                    ),
                    on_release=lambda instance: self._ok(instance),
                ),
                spacing=dp(8),
            ),
        )
        self.dialog.state_press = 0
        self.dialog.open()


def confirm_arbitrary_code(title: str, text: str, config_key: str,
                           on_confirm: Callable[[], None], confirm_text: str = "Continue"):
    """Run `on_confirm` behind an arbitrary-code warning dialog, unless the
    user suppressed the warning via the given `[security]` config key
    (read with fallback=False -- dynamic keys need no setdefaults)."""
    app = MDApp.get_running_app()
    try:
        suppressed = app.app_config.getboolean('security', config_key, fallback=False)
    except Exception as e:
        logger.error(f"Failed to read warning suppression '{config_key}': {e}", exc_info=True)
        suppressed = False
    if suppressed:
        on_confirm()
        return
    CodeWarningBox(
        title=title,
        message=text,
        callback=lambda ok: on_confirm() if ok else None,
        confirm_text=confirm_text,
        suppress_config_key=config_key,
    ).open()


class ConsoleBox(MDDialog):
    """
    Interactive console-style prompt with a text input; used for slot name
    and password prompts (input is masked when the prompt mentions a
    password).
    """
    
    def __init__(self, title="", prompt=""):
        super().__init__()
        self.title = title
        self.prompt = prompt
        self.app = MDApp.get_running_app()
        self.dialog = None
        self.text_input = None
    
    def _submit(self, instance):
        """Handle submit button press."""
        if hasattr(self.app.ctx, 'input_requests') and self.app.ctx.input_requests > 0:
            self.app.ctx.input_requests -= 1
            self.app.ctx.input_queue.put_nowait(self.text_input.text)
        self.dialog.dismiss()
        self.dialog = None
    
    def _cancel(self, instance):
        """Handle cancel button press."""
        self.dialog.dismiss()
        self.dialog = None
        
    def open(self):
        """Opens the dialog and displays it to the user."""
        if 'password' in self.prompt.lower():
            self.is_password = True
        else:
            self.is_password = False
        self.text_input = MDTextField(
            password=self.is_password,
            mode="outlined",
            size_hint_y=None,
            height=dp(56),
            on_text_validate=self._submit,
        )
        
        button_container = MDDialogButtonContainer(
            Widget(),
            MDButton(
                MDButtonText(
                    text="Cancel",
                    theme_text_color="Custom",
                    text_color=self.app.theme_cls.onSurfaceColor,
                ),
                on_release=self._cancel,
            ),
            MDButton(
                MDButtonText(
                    text="Submit",
                    theme_text_color="Custom",
                    text_color=self.app.theme_cls.primaryColor,
                ),
                on_release=self._submit,
            ),
            spacing=dp(8),
        )
        
        self.dialog = MDDialog(
            MDDialogHeadlineText(
                text=self.title,
            ),
            MDDialogSupportingText(
                text=self.prompt,
                theme_text_color="Primary",
                text_color=self.app.theme_cls.onSurfaceColor,
            ),
            self.text_input,
            button_container,
        )
        self.dialog.state_press = 0
        self.dialog.open()
        
        if self.text_input:
            self.text_input.focus = True
