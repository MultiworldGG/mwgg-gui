"""

TODO: probably pull this out - users have /connect & we can make a reconnect
button rather than a whole ass dialog.

ConnectDialog -- reconnect UI for client-direct processes.

Client processes never build a launcher screen (see app.py's `_create_screen`
client-role guard), so a lost connection needs its own reconnect home. Four
fields (hostname/port/username/password), prefilled from `app.ctx`'s own
InitContext properties, mirror the launcher's old "Launch Settings" fields;
confirming calls `app.ctx.connect(...)` the same way the launcher's in-process
reconnect branch used to before every launch became a separate OS process.

Singleton-guarded: opening a second dialog while one is already up dismisses
the stale one first, mirroring the MessageBox/ConsoleBox pile-up fix (commit
9370dad, "Fix reconnect dialog pile-up") -- `open()` builds and shows a
*nested* MDDialog rather than opening itself, so `dismiss()` is overridden to
close that nested dialog instead of the (never-shown) outer one.
"""
from __future__ import annotations

__all__ = ("ConnectDialog",)

import asyncio
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
)
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText, MDTextFieldLeadingIcon

logger = logging.getLogger("Client")

# Module-level singleton guard -- see class docstring.
_active_dialog: "ConnectDialog | None" = None


class ConnectDialog(MDDialog):
    """Reconnect dialog for client-direct processes (see module docstring)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.dialog = None

    def open(self):
        global _active_dialog
        if _active_dialog is not None:
            _active_dialog.dismiss()
        _active_dialog = self

        ctx = self.app.ctx
        self.hostname_field = MDTextField(
            MDTextFieldLeadingIcon(icon="router-network"),
            MDTextFieldHintText(text="Server Address"),
            text=str(getattr(ctx, "hostname", "") or ""),
        )
        self.port_field = MDTextField(
            MDTextFieldLeadingIcon(icon="numeric"),
            MDTextFieldHintText(text="Port"),
            text=str(getattr(ctx, "port", "") or ""),
            input_filter="int",
        )
        self.username_field = MDTextField(
            MDTextFieldLeadingIcon(icon="ticket-account"),
            MDTextFieldHintText(text="Username"),
            text=str(getattr(ctx, "username", "") or ""),
        )
        self.password_field = MDTextField(
            MDTextFieldLeadingIcon(icon="lock"),
            MDTextFieldHintText(text="Password"),
            text=str(getattr(ctx, "password", "") or ""),
            password=True,
        )

        fields = MDBoxLayout(
            self.hostname_field,
            self.port_field,
            self.username_field,
            self.password_field,
            orientation="vertical",
            spacing=dp(15),
            adaptive_height=True,
        )

        self.dialog = MDDialog(
            MDDialogHeadlineText(text="Reconnect"),
            MDDialogContentContainer(fields),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="CANCEL"),
                    on_release=lambda *_: self.dismiss(),
                ),
                MDButton(
                    MDButtonText(text="RECONNECT"),
                    on_release=lambda *_: self._confirm(),
                ),
                spacing=dp(8),
            ),
        )
        self.dialog.state_press = 0
        self.dialog.open()

    def _confirm(self):
        host = (self.hostname_field.text or "").strip()
        port = (self.port_field.text or "").strip()
        username = (self.username_field.text or "").strip()
        password = self.password_field.text or ""
        if not host or not port:
            logger.warning("ConnectDialog: missing server address/port, ignoring reconnect")
            return

        # Embedding creds in the address userinfo alone is not enough:
        # server_loop() never parses them back into ctx._username/_password,
        # and CommonContext.username/password getters prefer those cached
        # values over anything in the address -- so an edited field would be
        # silently ignored. Assign through the setters (which is what
        # client_get_username()/client_get_password() actually consult)
        # before connecting.
        ctx = self.app.ctx
        ctx.username = username
        ctx.password = password

        if username:
            colon = ":" if password else ""
            address = f"{username}{colon}{password}@{host}:{port}"
        else:
            address = f"{host}:{port}"

        self.dismiss()
        Clock.schedule_once(lambda dt: self.app.loading_layout.show_loading(), 0)
        asyncio.create_task(self.app.ctx.connect(address))
        Clock.schedule_once(lambda dt: self.app.loading_layout.hide_loading(), 2)

    def dismiss(self, *args):
        """Close the nested dialog opened by `open()` (see class docstring)."""
        global _active_dialog
        if self.dialog is not None:
            self.dialog.dismiss(*args)
            self.dialog = None
        if _active_dialog is self:
            _active_dialog = None
