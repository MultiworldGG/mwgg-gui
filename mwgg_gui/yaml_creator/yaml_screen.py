"""
YamlScreen - the full-screen YAML creator.

Layout mirrors ConsoleScreen (left half = primary content, right half =
auxiliary view). Here:

    +--------------------+--------------------+
    | header / mode togg | YAML preview pane  |
    | options form       | (CodeInput)        |
    |                    |                    |
    +--------------------+--------------------+
    | BottomAppBar (Save / Cancel / Mode)     |
    +-----------------------------------------+

Screen lifecycle is lazy: registered into the screen manager only when
the launcher's "Create YAML" button fires (see app._create_screen), and
torn down on game connect.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import asynckivy
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.segmentedbutton import MDSegmentedButton, MDSegmentedButtonItem
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

import yaml

import Utils

from mwgg_gui.components.dialog import MessageBox
from mwgg_gui.overrides.innermdscreen import InnerMDScreen

from .options_form import PlayerOptionsForm
from .weighted_form import WeightedOptionsForm
from .world_data import WorldDataError, load_world_data
from .yaml_io import form_state_to_yaml
from .yaml_view import YamlPreview

logger = logging.getLogger("Client")

__all__ = ("YamlScreen",)


def _players_dir() -> str:
    """Settings-resolved Players directory (settings.generator.
    player_files_path): the exact dir Generate scans. `Utils.players_path`
    needs a beta core new enough to ship it; older cores fall back to the
    user_path default (never local_path: the install dir may not be
    writable)."""
    players_path = getattr(Utils, "players_path", None)
    if players_path is not None:
        return players_path()
    return Utils.user_path("Players")


Builder.load_string(
    """
<YamlScreen>:
    name: "yaml"

<HeaderCard>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(64)
    padding: [dp(8), dp(6)]
    spacing: dp(8)
    pos_hint: {"top": 1}
    radius: dp(8)
    elevation: 1
    md_bg_color: app.theme_cls.surfaceVariantColor
    MDTextField:
        id: player_name
        size_hint_x: 0.4
        height: dp(56)
        MDTextFieldHintText:
            text: "Player Name"
    MDSegmentedButton:
        id: mode_toggle
        size_hint_x: 0.6
        pos_hint: {"center_y": 0.5}
        MDSegmentedButtonItem:
            id: mode_player
            active: True
            MDSegmentButtonLabel:
                text: "Player Options"
        MDSegmentedButtonItem:
            id: mode_weighted
            MDSegmentButtonLabel:
                text: "Weighted"
    """
)


class HeaderCard(MDCard):
    pass


class YamlScreen(InnerMDScreen):
    name = "yaml"
    selected_game = ObjectProperty(None)
    app: MDApp

    def __init__(self, selected_game: tuple, **kwargs):
        self.app = MDApp.get_running_app()
        self.adjust_bottom_appbar = False #hmmmmm
        super().__init__(**kwargs)
        self.selected_game = selected_game  # (module_name, display_name)
        self.module_name, self.game_name = selected_game

        self._form = None  # current form widget
        self._mode = "player"
        # True while live sync is off: during Sync -> Form apply, or after the user kept manual edits.
        self._sync_paused = False
        # Coalesce on_change bursts (slider drags fire per pixel) to one render per frame.
        self._push_trigger = Clock.create_trigger(
            lambda _dt: self._push_to_preview(), 0
        )
        # Worker results keyed by visibility ("simple" / "complex"); consulted by _build_form_for.
        self._world_data: dict = {}
        # Extras captured on Sync -> Form (hand-written `triggers:` etc.);
        # held across form rebuilds and re-emitted on every push.
        self._yaml_extras: dict = {}
        self._game_extras: dict = {}

        # Defer build to next frame so geometry is settled.
        Clock.schedule_once(lambda dt: self._build(), 0)

    # ----- layout ---------------------------------------------------------

    def _build(self):
        # Two-pane split + action bar; InnerMDScreen already reserves the chrome space.
        self._grid = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, 1),
            spacing=dp(6),
            padding=[dp(6), dp(6)],
            theme_bg_color = "Custom",
            md_bg_color=self.theme_cls.surfaceContainerLowColor
        )

        # Left pane: pixel-sized wrapper boxes per region. MDScrollView's
        # size_hint cascade breaks as a sibling of a fixed-height widget
        # (the inner MDList renders at full minimum_height).
        self._left = MDBoxLayout(
            orientation="vertical",
            size_hint=(0.58, None),
            height=self._left_height(),
            spacing=dp(6),
            # theme_bg_color = "Custom",
            # md_bg_color = self.theme_cls.surfaceContainerColor
        )

        # --- header box: pixel-sized wrapper holding the HeaderCard.
        self._header_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(64),
        )
        self._header = HeaderCard()
        self._header.ids.player_name.text = ""
        self._header.ids.player_name.bind(
            text=lambda *_: self._push_to_preview()
        )
        # Bound in Python: in KV, `root` in the HeaderCard rule resolves to the card, not the screen.
        self._header.ids.mode_player.bind(
            active=lambda _i, a: a and self.set_mode("player")
        )
        self._header.ids.mode_weighted.bind(
            active=lambda _i, a: a and self.set_mode("weighted")
        )
        self._header_box.add_widget(self._header)
        self._left.add_widget(self._header_box)

        # --- scroll box: pixel-sized wrapper holding the MDScrollView.
        self._scroll_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=self._scroll_box_height(),
        )
        self._form_scroll = MDScrollView(
            size_hint_x=1,
            do_scroll_x=False,
        )
        self._scroll_box.add_widget(self._form_scroll)
        self._left.add_widget(self._scroll_box)

        Window.bind(height=self._on_window_resize)

        self._grid.add_widget(self._left)

        # Right pane: YAML preview
        self._preview = YamlPreview(
            game_name=self.game_name,
            on_sync=self._on_preview_sync,
            on_resync=self._resume_sync,
            known_options=self._known_option_names,
            size_hint_x=0.42,
        )
        self._grid.add_widget(self._preview)

        # Bottom action bar (plain Save / Cancel).
        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(12), dp(8)],
            spacing=dp(8),
        )
        bar.add_widget(MDLabel(size_hint_x=1))  # spacer
        cancel_btn = MDButton(MDButtonText(text="Cancel"), style="tonal")
        cancel_btn.bind(on_release=lambda *_: self.cancel())
        save_btn = MDButton(
            MDButtonIcon(icon="content-save"),
            MDButtonText(text="Save YAML"),
            style="filled",
        )
        save_btn.bind(on_release=lambda *_: self.save())
        bar.add_widget(cancel_btn)
        bar.add_widget(save_btn)
        self._left.add_widget(bar)
        # One vertical container: two-pane grid + action bar.
        root = MDBoxLayout(orientation="vertical", size_hint=(1, 1), padding=dp(20))
        root.add_widget(self._grid)
        self.add_widget(root)

        # The form is built in _on_world_data_loaded once the worker responds.
        self._show_loading("Loading options…")
        self._fetch_world_data("simple")

    # ----- pixel-height sizing --------------------------------------------

    # Chrome (title + top + bottom bars) reserved by every screen; raw
    # pixels, NOT dp; same constant as launcher.kv:8 and hintscreen.py:229.
    # god I hate hardcoding. We added a height calculator but sure, whatever.
    _CHROME_PX = 142

    def _left_height(self) -> float:
        """Total height of the _left pane: window minus chrome minus
        the bottom action bar minus the grid's vertical padding."""
        return max(
            dp(180),
            Window.height - self._CHROME_PX - dp(64) - dp(12),
        )

    def _scroll_box_height(self) -> float:
        """Height of the scroll box: _left height minus the header
        box's dp(64)."""
        return max(dp(120), self._left_height() - dp(64))

    def _on_window_resize(self, _window, _height):
        if getattr(self, "_left", None) is not None:
            self._left.height = self._left_height()
        if getattr(self, "_scroll_box", None) is not None:
            self._scroll_box.height = self._scroll_box_height()

    # ----- mode toggle ----------------------------------------------------

    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        visibility = "complex" if mode == "weighted" else "simple"
        # Overlay even when cached: panels populate async and half-built rows would show.
        self._show_loading(f"Loading {mode} options…")
        if visibility in self._world_data:
            self._build_form_for(visibility)
        else:
            self._fetch_world_data(visibility)

    # ----- worker plumbing -----------------------------------------------

    def _fetch_world_data(self, visibility: str):
        """Spawn the worker in a background thread. The result is
        marshalled back onto the Kivy main thread via Clock so we don't
        touch widgets from a non-UI thread."""
        game_name = self.game_name
        module_name = self.module_name

        def _run():
            try:
                data = load_world_data(game_name, visibility=visibility, module=module_name)
                Clock.schedule_once(
                    lambda dt: self._on_world_data_loaded(visibility, data), 0
                )
            except WorldDataError as e:
                logger.warning("yaml worker failed: %s", e, exc_info=False)
                if e.trace:
                    logger.warning("yaml worker trace:\n%s", e.trace)
                msg = str(e)
                Clock.schedule_once(
                    lambda dt: self._on_world_data_error(visibility, msg), 0
                )

        threading.Thread(target=_run, daemon=True, name="yaml-worker").start()

    def _on_world_data_loaded(self, visibility: str, data: dict):
        self._world_data[visibility] = data
        expected = "complex" if self._mode == "weighted" else "simple"
        # Render only if the user hasn't switched modes meanwhile; the
        # overlay stays up until the form dispatches on_ready.
        if visibility == expected:
            self._build_form_for(visibility)

    def _on_world_data_error(self, visibility: str, message: str):
        expected = "complex" if self._mode == "weighted" else "simple"
        if visibility != expected:
            return
        self._show_error(message)

    def _build_form_for(self, visibility: str):
        data = self._world_data.get(visibility)
        if data is None:
            return
        form = (
            WeightedOptionsForm(data)
            if visibility == "complex"
            else PlayerOptionsForm(data)
        )
        self._show_form(form)
        # Async build keeps the loading animation rendering (mirrors HintScreen.update_hints_list).
        asynckivy.start(form.populate())

    # ----- form / loading swap -------------------------------------------

    def _show_loading(self, _text: str):
        """Show the app-wide loading overlay (same as other slow ops).
        `text` is accepted but unused: the layout is animation-only."""
        self._set_scroll_child(MDLabel(text="", size_hint_y=None, height=dp(1)))
        try:
            self.app.loading_layout.show_loading()
        except Exception as e:
            logger.warning("loading_layout.show_loading failed: %s", e)

    def _hide_loading(self):
        try:
            self.app.loading_layout.hide_loading()
        except Exception as e:
            logger.warning("loading_layout.hide_loading failed: %s", e)

    def _show_error(self, text: str):
        self._hide_loading()
        self._set_scroll_child(
            MDLabel(
                text=f"Unable to load options:\n{text}",
                halign="center",
                theme_text_color="Error",
            )
        )

    def _show_form(self, form):
        """Swap the form into the left pane. The loading overlay stays up
        until the form fires `on_ready` (see OptionsForm)."""
        form.bind(on_change=lambda _i, _opts: self._push_trigger())
        form.bind(on_ready=lambda _i: self._on_form_ready())
        self._set_scroll_child(form)
        self._form = form

    def _on_form_ready(self):
        """All panels populated and option rows have applied defaults.
        Safe to drop the loading overlay and push the initial preview."""
        self._hide_loading()
        self._push_to_preview()

    def _set_scroll_child(self, widget):
        if self._form is not None:
            parent = self._form.parent
            if parent is not None:
                parent.remove_widget(self._form)
            self._form = None
        self._form_scroll.clear_widgets()
        self._scroll_box.clear_widgets()
        if getattr(widget, "self_scrolling", False):
            # A RecycleView-backed form owns its own viewport; nesting
            # it inside the shared MDScrollView would fight it for every
            # scroll gesture, so it replaces the scroll in the box.
            self._scroll_box.add_widget(widget)
        else:
            self._form_scroll.add_widget(widget)
            self._scroll_box.add_widget(self._form_scroll)

    # ----- preview sync ---------------------------------------------------

    def _render_canonical_yaml(self) -> str:
        """The YAML the form's current state would produce. Used both to
        push the live preview and (in `_on_preview_sync`) to check
        whether a synced preview text round-tripped losslessly."""
        if self._form is None:
            return ""
        player_name = (self._header.ids.player_name.text or "Player").strip()
        return form_state_to_yaml(
            player_name=player_name,
            game_name=self.game_name,
            options=self._form.collect(),
            extras=self._yaml_extras,
            game_extras=self._game_extras,
        )

    def _push_to_preview(self):
        if self._form is None or self._sync_paused:
            return
        text = self._render_canonical_yaml()
        if not self._preview.dirty or text == self._preview.get_text():
            self._preview.set_text(text)
            return
        # Manual edits disagree with the form. Pause BEFORE asking:
        # Cancel/scrim-dismiss never fire the callback and just leave sync
        # paused; the early-return above keeps dialogs from stacking.
        self._sync_paused = True
        self._preview.show_sync_paused()
        MessageBox(
            "Overwrite manual edits?",
            "You've edited the YAML by hand. Overwrite it with the "
            "form's values, or keep your edits? Keeping them pauses "
            "live updates until you press Resync.",
            callback=lambda ok: self._resume_sync() if ok else None,
            ok_text="Overwrite",
            cancel_text="Keep edits",
        ).open()

    def _resume_sync(self):
        # Re-render: the form may have changed while sync was paused.
        self._preview.dirty = False
        self._preview.hide_sync_paused()
        self._sync_paused = False
        self._push_to_preview()

    def _known_option_names(self):
        """Option names the current form owns; lets the preview pane
        classify hand-written game-section keys as extras on sync."""
        if self._form is None:
            return None
        return self._form.option_names()

    def _on_preview_sync(self, state):
        """User clicked Sync → Form in the preview pane."""
        # Gate pushes: the player-name write fires _push_to_preview
        # synchronously, before the form has applied the synced options.
        self._sync_paused = True
        try:
            # Hold every key the form doesn't own so pushes re-emit it.
            self._yaml_extras = state.get("__extras__") or {}
            self._game_extras = state.get("__game_extras__") or {}
            name = state.get("__name__")
            if name:
                self._header.ids.player_name.text = str(name)
            options = state.get("__options__") or {}
            if self._form is not None:
                self._form.apply(options)
        except Exception as e:
            # Never strand the UI paused: resume so the next form edit still syncs.
            logger.warning("Sync → Form failed to apply: %s", e, exc_info=True)
            self._preview.dirty = False
            self._preview.hide_sync_paused()
            self._sync_paused = False
            return

        # A clean parse isn't a lossless round-trip (comments, key order).
        # Clear dirty and resume only when the canonical render matches the
        # typed text verbatim; otherwise stay paused until Resync/overwrite.
        if self._render_canonical_yaml() == self._preview.get_text():
            self._preview.dirty = False
            self._preview.hide_sync_paused()
            self._sync_paused = False
        else:
            self._preview.dirty = True
            self._preview.show_sync_paused()

    # ----- save / cancel --------------------------------------------------

    def save(self):
        try:
            text = self._preview.get_text()
            # Parse once to validate before writing.
            yaml.safe_load(text)

            player_name = (self._header.ids.player_name.text or "Player").strip()
            players_dir = _players_dir()
            os.makedirs(players_dir, exist_ok=True)
            filename = f"{player_name}_{self.module_name}.yaml"
            filepath = os.path.join(players_dir, filename)
            if os.path.exists(filepath):
                # Players/ may hold hand-maintained YAMLs; never clobber without asking.
                MessageBox(
                    "Overwrite YAML?",
                    f"{filename} already exists in your Players folder. Overwrite it?",
                    callback=lambda ok: self._write_yaml(filepath, text) if ok else None,
                ).open()
                return
            self._write_yaml(filepath, text)
        except yaml.YAMLError as e:
            MessageBox(
                "YAML Error",
                f"Refusing to save invalid YAML:\n{e}",
                is_error=True,
            ).open()
        except Exception as e:
            logger.error("Failed to save YAML: %s", e, exc_info=True)
            MessageBox(
                "Save Error",
                f"Failed to save YAML: {e}",
                is_error=True,
            ).open()

    def _write_yaml(self, filepath, text):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            MessageBox(
                "YAML saved",
                f"Wrote {filepath}",
            ).open()
        except OSError as e:
            logger.error("Failed to save YAML: %s", e, exc_info=True)
            MessageBox(
                "Save Error",
                f"Failed to save YAML: {e}",
                is_error=True,
            ).open()

    def cancel(self):
        """Return to launcher without saving."""
        self.app.screen_manager.current = "launcher"

    # ----- top app bar override ------------------------------------------
    #
    # Show the game being authored in the server label; restored on
    # on_leave. A game connect removes the screen without on_leave, but
    # TopAppBar.update_server_info(ctx) rewrites the label anyway.

    _APPBAR_FALLBACK = "Not Connected"

    def _server_label(self):
        try:
            return self.app.top_appbar_layout.top_appbar.server_info_label
        except AttributeError:
            return None

    def on_enter(self, *args):
        label = self._server_label()
        if label is None:
            return
        self._prev_appbar_text = label.text
        label.text = f"Creating YAML: {self.game_name}"

    def on_leave(self, *args):
        label = self._server_label()
        if label is None:
            return
        label.text = getattr(self, "_prev_appbar_text", self._APPBAR_FALLBACK)
