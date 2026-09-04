"""
AdminLoginDialog -- gate in front of the Admin screen (see app.change_screen).

Asks for the host password, sends `!admin login` straight through the
command processor (no console echo, no history), and calls `on_success`
once CommonClient flips `ctx.admin` on the server's "Login successful"
reply. "Go back" leaves the user on the current screen.

Same nested-MDDialog shape as ConnectDialog: `open()` builds and shows an
inner MDDialog, so `dismiss()` closes that one.
"""
from __future__ import annotations

__all__ = ("AdminLoginDialog",)

import logging

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText, MDTextFieldLeadingIcon

logger = logging.getLogger("Client")

LOGIN_TIMEOUT = 5.0
_active_dialog: "AdminLoginDialog | None" = None


class AdminLoginDialog(MDDialog):
    """Host-login gate for the Admin screen (see module docstring)."""

    def __init__(self, on_success, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.on_success = on_success
        self.dialog = None
        self._poll = None
        self._deadline = 0.0

    def open(self):
        global _active_dialog
        if _active_dialog is not None:
            _active_dialog.dismiss()
        _active_dialog = self

        connected = bool(getattr(self.app.ctx, "server", None))
        self.password_field = MDTextField(
            MDTextFieldLeadingIcon(icon="lock"),
            MDTextFieldHintText(text="Admin password"),
            text=self.app.app_config.get('client', 'admin_password', fallback=''),
            password=True,
        )
        self.password_field.bind(on_text_validate=lambda *_: self._login())
        self.status_label = MDLabel(
            text="" if connected else "Not connected to a server.",
            theme_text_color="Custom",
            text_color=self.app.theme_cls.errorColor,
            adaptive_height=True,
        )
        self.login_button = MDButton(
            MDButtonText(text="LOG IN"),
            on_release=lambda *_: self._login(),
            disabled=not connected,
        )
        self.dialog = MDDialog(
            MDDialogHeadlineText(text="Admin login required"),
            MDDialogContentContainer(
                MDDialogSupportingText(text="The Admin console needs the server's host password."),
                MDBoxLayout(
                    self.password_field,
                    self.status_label,
                    orientation="vertical",
                    spacing=dp(12),
                    adaptive_height=True,
                ),
                orientation="vertical",
                spacing=dp(12),
            ),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="GO BACK"),
                    on_release=lambda *_: self.dismiss(),
                ),
                self.login_button,
                spacing=dp(8),
            ),
        )
        self.dialog.state_press = 0
        self.dialog.open()

    def _login(self):
        if self.login_button.disabled:
            return
        password = self.password_field.text or ""
        if not password:
            self.status_label.text = "Enter the admin password."
            return
        self.status_label.text = "Logging in..."
        self.login_button.disabled = True
        # Bypasses on_message: it would echo the password to the console and
        # keep it in the up-arrow history. The server broadcasts it masked.
        self.app.commandprocessor(f"!admin login {password}")
        self._deadline = Clock.get_time() + LOGIN_TIMEOUT
        self._poll = Clock.schedule_interval(self._check_login, 0.2)

    def _check_login(self, dt):
        if getattr(self.app.ctx, "admin", False):
            self._stop_poll()
            self.dismiss()
            self.on_success()
        elif Clock.get_time() >= self._deadline:
            self._stop_poll()
            self.status_label.text = "Login failed. Check the password and try again."
            self.login_button.disabled = False

    def _stop_poll(self):
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None

    def dismiss(self, *args):
        """Close the nested dialog opened by `open()` (see module docstring)."""
        global _active_dialog
        self._stop_poll()
        if self.dialog is not None:
            self.dialog.dismiss(*args)
            self.dialog = None
        if _active_dialog is self:
            _active_dialog = None
