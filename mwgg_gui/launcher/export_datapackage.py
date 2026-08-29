"""
Datapackage export dialog for the launcher.

Core's `Export Datapackage` component dumps `worlds.network_data_package`,
which in the launcher process only ever holds the generic baseline
(`Utils._worlds_to_load` defaults to generic + tracker). This dialog lets the
user pick any available games (customs included) and hands exactly those
modules to `Generate --export-datapackage` in a child process, which writes
the combined package to `datapackage_export.json`. Worlds never import into
the launcher, so exports stay repeatable within one launcher run.

The selection list reuses the yaml creator's `MassSelectViewRow` checkbox
rows: `ExportGamesContent` implements their `owner._set_selected` contract.
"""
from __future__ import annotations

__all__ = ("open_export_dialog", "export_selected_worlds")

import logging
import threading
from typing import Iterable

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (MDDialog,
                               MDDialogHeadlineText,
                               MDDialogContentContainer,
                               MDDialogButtonContainer)
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from mwgg_igdb import GameIndex

from mwgg_gui.components.dialog import MessageBox, confirm_arbitrary_code

logger = logging.getLogger("Client")


class ExportGamesContent(MDBoxLayout):
    """Search + select-all/clear controls over a checkbox RecycleView of the
    available games."""

    def __init__(self, entries: list[dict], **kwargs):
        # Deferred: pulls in the yaml_creator package, which the launcher
        # otherwise only loads when the YAML screen is first opened.
        from mwgg_gui.yaml_creator.mass_select import MassRecycleView

        super().__init__(orientation="vertical", spacing=dp(8),
                         adaptive_height=True, **kwargs)
        self._labels = {entry["module"]: entry["label"] for entry in entries}
        self._all_modules = [entry["module"] for entry in entries]
        self.selected: set[str] = set()

        self._search = MDTextField(
            MDTextFieldHintText(text="Search games..."),
            size_hint_y=None,
            height=dp(48),
        )
        self._search.bind(text=lambda _i, t: self._refresh(t))
        self.add_widget(self._search)

        self._summary = MDLabel(
            text=self._summary_text(),
            theme_text_color="Secondary",
            pos_hint={"center_y": 0.5},
        )
        select_all_button = MDButton(
            MDButtonText(text="SELECT ALL"), style="text",
            pos_hint={"center_y": 0.5})
        select_all_button.bind(on_release=lambda *_a: self._set_all(True))
        clear_button = MDButton(
            MDButtonText(text="CLEAR"), style="text",
            pos_hint={"center_y": 0.5})
        clear_button.bind(on_release=lambda *_a: self._set_all(False))
        self.add_widget(MDBoxLayout(
            self._summary,
            select_all_button,
            clear_button,
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(40),
        ))

        self._rv = MassRecycleView(
            size_hint_y=None,
            height=min(dp(280), max(dp(160), Window.height * 0.35)),
        )
        self.add_widget(self._rv)
        self._refresh("")

    def _refresh(self, query: str):
        q = (query or "").strip().lower()
        if q:
            modules = [m for m in self._all_modules if q in self._labels[m].lower()]
        else:
            # Selected first; reorder only on query change so rows don't jump
            # under the cursor on toggle.
            modules = [m for m in self._all_modules if m in self.selected] + [
                m for m in self._all_modules if m not in self.selected
            ]
        self._rv.data = [
            {
                "label": self._labels[m],
                "key": m,
                "selected": m in self.selected,
                "owner": self,
            }
            for m in modules
        ]

    def _set_selected(self, key: str, active: bool):
        if active:
            self.selected.add(key)
        else:
            self.selected.discard(key)
        self._summary.text = self._summary_text()
        # Freshen in place (no reorder) so a recycled row can't reapply a
        # stale `selected` and undo the toggle.
        for entry in self._rv.data:
            if entry["key"] == key:
                entry["selected"] = active
                break

    def _set_all(self, active: bool):
        self.selected = set(self._all_modules) if active else set()
        self._summary.text = self._summary_text()
        self._refresh(self._search.text)

    def _summary_text(self) -> str:
        return f"{len(self.selected)} of {len(self._all_modules)} selected"


def _selectable_games(screen) -> list[dict]:
    """(module, display label) for every available world, customs marked.
    Underscore modules are game-agnostic client helpers, not games."""
    customs = set(screen._custom_world_modules)
    entries = []
    for module in screen.available_games:
        if module.startswith("_"):
            continue
        name = GameIndex.get_game_name_for_module(module) or module
        entries.append({
            "module": module,
            "label": f"{name} (custom)" if module in customs else name,
        })
    entries.sort(key=lambda entry: entry["label"].lower())
    return entries


def open_export_dialog(screen) -> None:
    """Open the game-selection dialog; `screen` is the LauncherScreen."""
    entries = _selectable_games(screen)
    if not entries:
        MessageBox("Export Datapackage",
                   "No games are available to export yet.",
                   is_error=True).open()
        return
    content = ExportGamesContent(entries)
    dialog = MDDialog(
        MDDialogHeadlineText(
            text="Export Datapackage",
        ),
        MDDialogContentContainer(content),
        MDDialogButtonContainer(
            MDButton(
                MDButtonText(text="CANCEL"),
                on_release=lambda x: dialog.dismiss()
            ),
            MDButton(
                MDButtonText(text="EXPORT"),
                on_release=lambda x: _confirm_export(screen, dialog, content)
            ),
            spacing=dp(8),
        ),
    )
    dialog.open()


def _confirm_export(screen, dialog, content: ExportGamesContent) -> None:
    modules = sorted(content.selected)
    if not modules:
        screen.show_snackbar("Select at least one game to export.", is_error=True)
        return
    customs = sorted(set(modules) & set(screen._custom_world_modules))

    def proceed():
        dialog.dismiss()
        _run_export(modules)

    if customs:
        confirm_arbitrary_code(
            "Export Datapackage",
            "Exporting loads each selected world's code on your computer. "
            "The selection includes manually installed (custom) worlds; only "
            "continue if you trust where they came from.",
            "export_datapackage_warning_ok",
            proceed,
            confirm_text="Export",
        )
    else:
        proceed()


def _run_export(modules: list[str]) -> None:
    """Run the export child on a worker thread behind the loading overlay."""
    app = MDApp.get_running_app()
    Clock.schedule_once(lambda dt: app.loading_layout.show_loading(display_logs=True), 0)

    def worker():
        try:
            path, failed = export_selected_worlds(modules)
        except Exception as e:
            logger.exception("Datapackage export failed")
            if getattr(e, "trace", None):
                logger.error(e.trace)

            def show_error(dt, err=e):
                app.loading_layout.hide_loading()
                MessageBox("Export Failed",
                           f"Datapackage export failed: {err}",
                           is_error=True).open()

            Clock.schedule_once(show_error, 0)
            return

        def show_done(dt):
            app.loading_layout.hide_loading()
            if failed:
                MessageBox("Export Finished",
                           f"Datapackage exported to {path}, but these worlds "
                           f"failed to load: {', '.join(failed)}",
                           is_error=True).open()
            else:
                MessageBox("Export Complete",
                           f"Datapackage exported to {path}.").open()
            from Utils import open_file
            open_file(path)

        Clock.schedule_once(show_done, 0)

    threading.Thread(target=worker, name="mwgg-datapackage-export", daemon=True).start()


# Many worlds plus cold installs: well past world_data's per-world timeout.
_EXPORT_TIMEOUT_SECONDS = 1800


def export_selected_worlds(modules: Iterable[str]) -> tuple[str, list[str]]:
    """Export `modules` via `Generate --export-datapackage` in a child process.
    Returns (path, modules_that_failed_to_load); caller handles the UI."""
    # Deferred: yaml_creator is the launcher's out-of-process Generate client.
    from mwgg_gui.yaml_creator.world_data import run_generate_json

    payload = run_generate_json(["--export-datapackage", *modules], timeout=_EXPORT_TIMEOUT_SECONDS)
    return payload["path"], list(payload.get("failed", ()))
