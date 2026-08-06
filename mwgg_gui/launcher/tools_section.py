"""
Tools pane -- the "Tools" side of the launcher's Play/Tools toggle.

`worlds.LauncherComponents` is the shared registry the monorepo's client,
headless Launcher, and this GUI all consume (`launcher.py` already imports
`worlds.LauncherComponents.spawn_client` the same lazy way). Importing it
eagerly at module import time would make the whole launcher screen pay for
that import before a single game tile renders, so `ToolsSection.bootstrap()`
defers it to a background thread and only touches Kivy widgets back on the
main thread via `Clock`.

Entries are `builtin_components()` (origin-filtered, so a `.apworld` install
or a late world import can't smuggle a stray component into the grid) minus
`Type.HIDDEN`, dispatched through an override map for the handful of
components whose real UI already lives in `LauncherScreen`'s existing dialog
flows (Generate/Host/Text Client), plus two GUI-local entries (Patch Game /
Create YAML) that have no `LauncherComponents` equivalent at all.
"""
from __future__ import annotations

__all__ = ("ToolEntry", "ToolCard", "ToolsSection")

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.image import Image
from kivymd.app import MDApp
from kivymd.uix.card import MDCard
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDIcon
from kivymd.uix.scrollview import MDScrollView

logger = logging.getLogger("Client")

Builder.load_string(
    """
<ToolCard>:
    orientation: "vertical"
    size_hint: None, None
    size: dp(220), dp(150)
    padding: dp(12)
    spacing: dp(6)
    radius: dp(12)
    elevation: 1
    ripple_behavior: True
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.surfaceContainerColor
    on_release: root.activate()
    AnchorLayout:
        id: icon_slot
        size_hint_y: None
        height: dp(56)
    MDLabel:
        text: root.title
        halign: "center"
        theme_font_style: "Custom"
        font_style: "Title"
        role: "small"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceColor
        size_hint_y: None
        height: self.texture_size[1]
    MDLabel:
        text: root.description
        halign: "center"
        theme_font_style: "Custom"
        font_style: "Body"
        role: "small"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceVariantColor

<ToolsSection>:
    do_scroll_x: False
    grid: grid
    MDGridLayout:
        id: grid
        cols: 2
        adaptive_height: True
        spacing: dp(16)
        padding: dp(4)
        size_hint_y: None
        height: self.minimum_height
    """
)


@dataclass
class ToolEntry:
    """One grid entry: either a wrapped `LauncherComponents.Component`, or a
    GUI-local action (Patch Game / Create YAML) with no component equivalent.

    Exactly one of `icon_name` (a plain md icon glyph, for GUI-local entries)
    or `icon_source` (a resolved image file path, for components -- see
    `LauncherComponents.resolve_icon_path`) is set.
    """
    title: str
    description: str
    activate: Callable[[], None]
    icon_name: Optional[str] = None
    icon_source: Optional[str] = None


class ToolCard(MDCard):
    title = StringProperty("")
    description = StringProperty("")

    def __init__(self, entry: ToolEntry, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry
        self.title = entry.title
        self.description = entry.description
        if entry.icon_name:
            icon_widget = MDIcon(
                icon=entry.icon_name,
                font_size=dp(48),
                theme_icon_color="Custom",
                icon_color=self.theme_cls.primaryColor,
            )
        else:
            icon_widget = Image(
                source=entry.icon_source,
                size_hint=(None, None),
                size=(dp(48), dp(48)),
                pos_hint={"center_x": 0.5},
            )
        self.ids.icon_slot.add_widget(icon_widget)

    def activate(self):
        """Whole-card click target. Disabled for the duration of the
        synchronous dispatch so a double-click can't fire a tool twice --
        most entries return immediately (spawn a detached process or open a
        file picker), so there's no need to track completion beyond that."""
        if self.disabled:
            return
        self.disabled = True
        try:
            self.entry.activate()
        except Exception as e:
            logger.error("Tool %r failed: %s", self.title, e, exc_info=True)
        finally:
            self.disabled = False


class ToolsSection(MDScrollView):
    grid = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self._bootstrapped = False
        self._launcher_components = None

    def bootstrap(self):
        """Lazily import worlds.LauncherComponents off the main thread and
        build the grid once it lands. Idempotent -- safe to call every time
        the Tools screen is entered."""
        if self._bootstrapped:
            return
        self._bootstrapped = True

        def _load():
            try:
                import worlds.LauncherComponents as launcher_components
            except Exception:
                logger.exception("Tools section: failed to import worlds.LauncherComponents")
                return
            self._launcher_components = launcher_components
            # Claim the post-Install-APWorld refresh hook.
            launcher_components._rebuild_launcher_ui = lambda *a: Clock.schedule_once(self._on_apworld_installed)
            Clock.schedule_once(self.rebuild)

        threading.Thread(target=_load, name="mwgg-tools-bootstrap", daemon=True).start()

    def rebuild(self, *_args):
        """(Re)build the grid. Runs on the main thread: called directly by
        `bootstrap()`'s worker via Clock, and again via `_on_apworld_installed`."""
        launcher_components = self._launcher_components
        if launcher_components is None or self.grid is None:
            return
        self.grid.clear_widgets()
        for entry in self.build_entries(launcher_components):
            self.grid.add_widget(ToolCard(entry))

    def _on_apworld_installed(self, *_args):
        """`LauncherComponents._rebuild_launcher_ui` hook. Repaints the tools
        grid (a new component may have registered) and, if a launcher screen
        exists, re-scans available worlds and rebuilds the game list so a
        freshly installed .apworld shows up without a restart. Runs on the
        main thread (called via Clock) and is feature-detected so it can't
        crash if the launcher screen was never built (client-role process)."""
        self.rebuild()
        launcher_screen = getattr(self.app, "launcher_screen", None)
        if launcher_screen is None or not hasattr(launcher_screen, "set_game_list"):
            return
        try:
            import asynckivy
            from Utils import get_available_worlds
            launcher_screen.available_games = get_available_worlds()
            asynckivy.start(launcher_screen.set_game_list())
        except Exception:
            logger.exception("Tools section: failed to refresh launcher game list after install")

    def build_entries(self, launcher_components) -> list[ToolEntry]:
        launcher_screen = getattr(self.app, "launcher_screen", None)
        component_type = launcher_components.Type

        overrides: dict[str, Callable[[], None]] = {}
        if launcher_screen is not None:
            overrides = {
                "Generate": launcher_screen.generate,
                "Host": launcher_screen.host,
                # Never component.func here -- it would spawn a Text Client
                # from the component's own context, without the launcher's
                # server/slot/password field values.
                "Text Client": launcher_screen.spawn_text_client,
            }

        entries: list[ToolEntry] = []
        for component in launcher_components.builtin_components():
            if component.type is component_type.HIDDEN:
                continue
            activate = overrides.get(component.display_name)
            if activate is None:
                activate = self._default_activator(launcher_components, component)
            icon_path = launcher_components.icon_paths.get(
                component.icon, launcher_components.icon_paths["icon"]
            )
            entries.append(ToolEntry(
                title=component.display_name,
                description=component.description,
                activate=activate,
                icon_source=launcher_components.resolve_icon_path(icon_path),
            ))

        if launcher_screen is not None:
            entries.append(ToolEntry(
                title="Patch Game",
                description="Apply a patch file to produce a playable game copy.",
                activate=launcher_screen.patch_game,
                icon_name="file-edit",
            ))
            entries.append(ToolEntry(
                title="Create YAML",
                description="Author a Players/ YAML for the selected game (select a game first).",
                activate=launcher_screen.create_yaml,
                icon_name="code-block-brackets",
            ))

        return entries

    @staticmethod
    def _default_activator(launcher_components, component) -> Callable[[], None]:
        if component.func:
            return component.func
        return lambda: launcher_components.run_component(component)
