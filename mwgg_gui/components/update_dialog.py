"""
UpdateDialog -- app-installer update prompt for the launcher process.

Opened by MultiMDApp's launcher-role background update check (see
app.py `_start_update_check`) when the monorepo's `Updater` module reports a
GitHub release newer than the running version. Shows current -> new version
plus the release changelog body, with Later / Update Now buttons.

Update Now on Windows swaps to a small progress dialog and runs
`Updater.download_and_install_win(url, progress_callback=...)` in a daemon
thread -- that call hands off to the Inno installer (/TASKS=deletelib) and
terminates this process itself, so nothing here runs after success. On other
platforms auto-install is not ported yet, so we open the GitHub release page
in the browser and dismiss.

Follows the MessageBox/ConnectDialog pattern: `open()` builds and shows a
*nested* MDDialog rather than opening itself, and `dismiss()` closes that
nested dialog instead of the (never-shown) outer one.
"""
from __future__ import annotations

__all__ = ("UpdateDialog",)

import logging
import sys
import threading
import webbrowser

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
from kivymd.uix.progressindicator import MDLinearProgressIndicator
from kivymd.uix.scrollview import MDScrollView

logger = logging.getLogger("Client")


def _version_string(version) -> str:
    """BaseUtils.Version has as_simple_string(); tolerate plain tuples/strings."""
    as_simple = getattr(version, "as_simple_string", None)
    if as_simple is not None:
        return as_simple()
    if isinstance(version, tuple):
        return ".".join(str(part) for part in version)
    return str(version)


class UpdateDialog(MDDialog):
    """Update prompt for the launcher process (see module docstring)."""

    def __init__(self, current_version, new_version, changelog: str,
                 download_url: str, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.current_version = current_version
        self.new_version = new_version
        self.changelog = changelog
        self.download_url = download_url
        self.dialog = None
        self.progress_dialog = None
        self.progress_bar = None
        self.progress_label = None

    def open(self):
        changelog_label = MDLabel(
            text=self.changelog,
            size_hint_y=None,
            halign="left",
            valign="top",
            font_style="Body",
            role="small",
            padding=(dp(4), dp(4)),
        )
        changelog_label.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val, None))
        )
        changelog_label.bind(
            texture_size=lambda inst, val: setattr(inst, "height", val[1])
        )

        changelog_scroll = MDScrollView(
            changelog_label,
            size_hint_y=None,
            height=dp(280),
            do_scroll_x=False,
        )

        self.dialog = MDDialog(
            MDDialogHeadlineText(text="Update Available"),
            MDDialogSupportingText(
                text=(
                    f"MultiworldGG {_version_string(self.new_version)} is available. "
                    f"You are currently using version {_version_string(self.current_version)}.\n"
                    "If you are currently playing a game listed in the changelog, "
                    "consider finishing it before updating."
                ),
            ),
            MDDialogContentContainer(changelog_scroll),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Later"),
                    on_release=lambda *_: self.dismiss(),
                ),
                MDButton(
                    MDButtonText(text="Update Now"),
                    on_release=lambda *_: self._on_update_now(),
                ),
                spacing=dp(8),
            ),
        )
        self.dialog.state_press = 0
        self.dialog.open()

    def _on_update_now(self):
        self.dismiss()
        if sys.platform == "win32":
            self._start_windows_download()
        else:
            # Auto-install is not ported for this platform yet: send the user
            # to the release page instead (Updater.get_release_page_url).
            import Updater
            webbrowser.open(Updater.get_release_page_url())

    def _start_windows_download(self):
        self.progress_label = MDLabel(
            text="Downloading update...",
            halign="center",
            adaptive_height=True,
        )
        self.progress_bar = MDLinearProgressIndicator(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(8),
        )
        body = MDBoxLayout(
            self.progress_label,
            self.progress_bar,
            orientation="vertical",
            spacing=dp(12),
            adaptive_height=True,
        )
        self.progress_dialog = MDDialog(
            MDDialogHeadlineText(text="Downloading Update"),
            MDDialogContentContainer(body),
            auto_dismiss=False,
        )
        self.progress_dialog.state_press = 0
        self.progress_dialog.open()

        threading.Thread(
            target=self._download_worker, name="UpdateDownload", daemon=True
        ).start()

    def _download_worker(self):
        import Updater
        try:
            # Hands off to the Inno installer and calls os._exit(0) on success.
            Updater.download_and_install_win(
                self.download_url, progress_callback=self._on_progress
            )
        except Exception as e:
            logger.error("Update failed: %s", e)
            Clock.schedule_once(lambda dt: self._show_download_error(e))

    def _on_progress(self, downloaded: int, total: int):
        def _update(dt):
            if self.progress_bar is None or self.progress_label is None:
                return
            mb_done = downloaded / 1_048_576
            if total > 0:
                self.progress_bar.value = downloaded / total * 100
                mb_total = total / 1_048_576
                self.progress_label.text = (
                    f"Downloading update... {mb_done:.1f} / {mb_total:.1f} MB"
                )
            else:
                self.progress_label.text = f"Downloading update... {mb_done:.1f} MB"
        Clock.schedule_once(_update)

    def _show_download_error(self, error: Exception):
        if self.progress_label is not None:
            self.progress_label.text = f"Update failed: {error}"
        if self.progress_bar is not None:
            self.progress_bar.value = 0
        if self.progress_dialog is not None:
            # Let the user click away a failed download.
            self.progress_dialog.auto_dismiss = True

    def dismiss(self, *args):
        """Close the nested dialog opened by `open()` (see module docstring)."""
        if self.dialog is not None:
            self.dialog.dismiss(*args)
            self.dialog = None
