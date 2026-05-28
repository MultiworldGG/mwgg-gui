"""
YamlScreen — the full-screen YAML creator.

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

from Utils import local_path

from mwgg_gui.components.dialog import MessageBox
from mwgg_gui.overrides.innermdscreen import InnerMDScreen

from .options_form import PlayerOptionsForm, WeightedOptionsForm
from .world_data import WorldDataError, load_world_data
from .yaml_io import form_state_to_yaml
from .yaml_view import YamlPreview

logger = logging.getLogger("Client")

__all__ = ("YamlScreen",)


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
    radius: dp(8)
    elevation: 1
    md_bg_color: app.theme_cls.surfaceVariantColor
    MDTextField:
        id: player_name
        size_hint_x: 0.45
        MDTextFieldHintText:
            text: "Player name"
    MDSegmentedButton:
        id: mode_toggle
        size_hint_x: 0.55
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
        super().__init__(**kwargs)
        self.selected_game = selected_game  # (module_name, display_name)
        self.module_name, self.game_name = selected_game

        self._form = None  # current form widget
        self._mode = "player"
        # Worker results, keyed by visibility ("simple" / "complex").
        # Populated asynchronously; consulted by _show_form.
        self._world_data: dict = {}

        # Defer build to next frame so geometry is settled.
        Clock.schedule_once(lambda dt: self._build(), 0)

    # ----- layout ---------------------------------------------------------

    def _build(self):
        # Two-pane horizontal split, with an action bar beneath. The
        # surrounding InnerMDScreen has already reserved space for the
        # title bar, top app bar, and bottom app bar.
        self._grid = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, 1),
            spacing=dp(6),
            padding=[dp(6), dp(6)],
        )

        # Left pane: an explicitly-sized vertical container that holds
        # two more explicitly-sized boxes — one for the header, one for
        # the scroll. MDScrollView's size_hint cascade does NOT work
        # when it's a size_hint sibling of a fixed-height widget inside
        # a single BoxLayout (the inner MDList ends up rendering at
        # full minimum_height); the workaround is to wrap each region
        # in its own pixel-sized container.
        self._left = MDBoxLayout(
            orientation="vertical",
            size_hint=(0.58, None),
            height=self._left_height(),
            spacing=dp(6),
        )

        # --- header box: pixel-sized wrapper holding the HeaderCard.
        self._header_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(64),
        )
        self._header = HeaderCard()
        self._header.ids.player_name.text = "Player"
        self._header.ids.player_name.bind(
            text=lambda *_: self._push_to_preview()
        )
        # Bind the mode-toggle segments in Python so `self` (the screen)
        # is the callback target. In KV, `root` inside the HeaderCard
        # rule resolves to the HeaderCard, not the screen.
        self._header.ids.mode_player.bind(
            active=lambda _i, a: a and self.set_mode("player")
        )
        self._header.ids.mode_weighted.bind(
            active=lambda _i, a: a and self.set_mode("weighted")
        )
        self._header_box.add_widget(self._header)
        self._left.add_widget(self._header_box)

        # --- scroll box: pixel-sized wrapper holding the MDScrollView.
        # The scroll uses size_hint_x=1 (fill the box horizontally) and
        # default size_hint_y=1 (fill the box vertically — which works
        # cleanly now that the box itself has an explicit pixel height).
        self._scroll_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=self._scroll_box_height(),
        )
        self._form_scroll = MDScrollView(
            size_hint_x=1,
            bar_width=dp(4),
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

        # InnerMDScreen handles the chrome offset for us; we just need
        # one vertical container holding the two-pane grid + action bar.
        root = MDBoxLayout(orientation="vertical", size_hint=(1, 1))
        root.add_widget(self._grid)
        root.add_widget(bar)
        self.add_widget(root)

        # Kick off the worker for the initial mode. The form gets built
        # in _on_world_data_loaded once the response is in.
        self._show_loading("Loading options…")
        self._fetch_world_data("simple")

    # ----- pixel-height sizing --------------------------------------------

    # Chrome (title bar + top app bar + bottom app bar) reserved by
    # every screen in this app — raw pixels, same constant as
    # `launcher.kv:8` and `hintscreen.py:229`. NOT a dp value.
    _CHROME_PX = 185

    def _left_height(self) -> float:
        """Total height of the _left pane: window minus chrome minus
        the bottom action bar minus the grid's vertical padding."""
        return max(
            dp(180),
            Window.height - self._CHROME_PX - dp(56) - dp(12),
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
        # Always show the loading overlay during the rebuild — even when
        # data is cached, the new form's panels populate asynchronously
        # and we don't want the user to see half-built rows.
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

        def _run():
            try:
                data = load_world_data(game_name, visibility=visibility)
                Clock.schedule_once(
                    lambda dt: self._on_world_data_loaded(visibility, data), 0
                )
            except WorldDataError as e:
                logger.warning("yaml worker failed: %s", e, exc_info=False)
                if e.trace:
                    logger.debug("yaml worker trace:\n%s", e.trace)
                msg = str(e)
                Clock.schedule_once(
                    lambda dt: self._on_world_data_error(visibility, msg), 0
                )

        threading.Thread(target=_run, daemon=True, name="yaml-worker").start()

    def _on_world_data_loaded(self, visibility: str, data: dict):
        self._world_data[visibility] = data
        expected = "complex" if self._mode == "weighted" else "simple"
        # Only render if the user hasn't switched away while we were
        # waiting; otherwise stash the data for when they come back.
        # `_show_form` keeps the loading overlay up until the form
        # dispatches on_ready — no preview push needed here.
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
        # Build panels asynchronously so the loading animation keeps
        # rendering during the heavy widget construction (KH2 ~45
        # panels, some worlds much more). Mirrors
        # `HintScreen.update_hints_list` →
        # `asynckivy.start(self.set_hints_list())` in
        # mwgg_gui/hint/hintscreen.py:275.
        asynckivy.start(form.populate())

    # ----- form / loading swap -------------------------------------------

    def _show_loading(self, _text: str):
        """Show the app-wide loading animation while the worker runs.

        The full-screen overlay is what we already use for other slow
        ops (font reload, theme change, generate); reusing it keeps the
        UX consistent. The `text` arg is accepted but currently unused —
        the loading layout is animation-only.
        """
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
        """Swap the form into the left pane. Loading overlay stays up
        until the form fires `on_ready` — see OptionsForm — so the
        chrome doesn't drop while panels are still building."""
        form.bind(on_change=lambda _i, _opts: self._push_to_preview())
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
            self._form_scroll.remove_widget(self._form)
            self._form = None
        # The scroll view holds at most one child; clear and add fresh.
        self._form_scroll.clear_widgets()
        self._form_scroll.add_widget(widget)

    # ----- preview sync ---------------------------------------------------

    def _push_to_preview(self):
        if self._form is None:
            return
        player_name = (self._header.ids.player_name.text or "Player").strip()
        collected = self._form.collect()
        logger.info("yaml_creator: _push_to_preview, collected=%r", collected)
        text = form_state_to_yaml(
            player_name=player_name,
            game_name=self.game_name,
            options=collected,
        )
        self._preview.set_text(text)

    def _on_preview_sync(self, state):
        """User clicked Sync → Form in the preview pane."""
        name = state.get("__name__")
        if name:
            self._header.ids.player_name.text = str(name)
        options = state.get("__options__") or {}
        if self._form is not None:
            self._form.apply(options)
        # Don't push back to preview — the user's text already matches.

    # ----- save / cancel --------------------------------------------------

    def save(self):
        try:
            text = self._preview.get_text()
            # Parse once to validate before writing.
            yaml.safe_load(text)

            player_name = (self._header.ids.player_name.text or "Player").strip()
            players_dir = local_path("Players")
            os.makedirs(players_dir, exist_ok=True)
            filename = f"{player_name}_{self.module_name}.yaml"
            filepath = os.path.join(players_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            MessageBox(
                "YAML saved",
                f"Wrote {filepath}",
            ).open()
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

    def cancel(self):
        """Return to launcher without saving."""
        self.app.screen_manager.current = "launcher"

    # ----- top app bar override ------------------------------------------
    #
    # While the YAML creator is up, swap the top app bar's server label
    # to advertise which game we're authoring for — "Not Connected" is
    # the right text on the launcher but unhelpful here. We restore the
    # previous text on `on_leave`. If a game connects while we're on
    # this screen, `on_connect` removes us via `remove_widget` (no
    # `on_leave` fires), but the connection flow rewrites the label
    # via `TopAppBar.update_server_info(ctx)` anyway, so the stale
    # game-name text gets overwritten immediately. No extra cleanup
    # needed for that path.

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
