from __future__ import annotations
"""
LAUNCHER SCREEN

LauncherScreen - main screen for displaying the launcher
LauncherLayout - layout for the launcher screen
LauncherView - view for the launcher screen

Includes the following:
- FavoritesScroll - horizontal scroller for favorite games
"""

__all__ = ('LauncherScreen', 
           'LauncherLayout', 
           'LauncherView', 
           'LauncherAuthTextField'
           )
import asynckivy
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, ObjectProperty, ListProperty
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.properties import ObjectProperty
from kivymd.uix.sliverappbar import MDSliverAppbar
from kivymd.theming import ThemableBehavior
from kivymd.uix.list import MDList
from kivymd.uix.navigationdrawer import (MDNavigationLayout,
                                         MDNavigationDrawer,
                                         MDNavigationDrawerDivider)
from kivymd.uix.navigationdrawer.navigationdrawer import MDNavigationDrawerItem
from kivymd.uix.textfield import MDTextField
from kivymd.uix.dialog import (MDDialog, 
                               MDDialogHeadlineText, 
                               MDDialogContentContainer,
                               MDDialogButtonContainer)
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText


import logging
from dataclasses import dataclass
from typing import Any
import tempfile
import shutil
import zipfile
import os
import sys
from pathlib import Path
import subprocess
import threading
import urllib.parse
import webbrowser

from kivymd.app import MDApp
from mwgg_igdb import GameIndex

from mwgg_gui.overrides.expansionlist import *
from mwgg_gui.components.bottomappbar import BottomAppBar
from mwgg_gui.components.nav_drawer import NavDrawerMenu, NavDrawerLabel
from mwgg_gui.launcher.launcher_sliver_appbar import LauncherSliverAppbar
from mwgg_gui.launcher.launcher_favorite_bar import FavoritesScroll, Favorite
from mwgg_gui.components.dialog import MessageBox
from mwgg_gui.launcher.setup_guide import (extract_bundled_setup_doc,
                                           open_with_desktop,
                                           setup_guide_url)
import Utils
from Utils import (get_available_worlds,
                   user_path,
                   local_path,
                   is_frozen,
                   is_windows,
                   persistent_store)
from frontend_protocol import verify_slot, SlotVerifyResult

from FileUtils import FileUtils

logger = logging.getLogger("Client")

# Game-agnostic modules (multi-game or no-game clients) skip pre-flight Connect
# verification: the server's game name won't match one canonical client identity.
_SKIP_GAME_VALIDATION_MODULES = {"_bizhawk", "_sni", "_tracker"}

# Shown whenever no game is selected. The backend represents that state as the
# generic "Archipelago" game (the text-client fallback slots Generate emits for
# game-less players); the UI deliberately never surfaces that name.
_NO_GAME_STATUS = ("Game not set, connecting using Text Client. "
                   "Switch to Universal Tracker or set your game.")


def _needs_game_validation(game_module: str, game_label: str) -> bool:
    """True if the launcher should pre-flight a Connect handshake against the
    server before flipping into the per-game client.

    Game-agnostic modules (text client fallback when nothing is selected, plus
    `_bizhawk` / `_sni` / `_tracker`) skip verification -- they're designed to
    connect to whatever the server has at that slot.
    """
    if not game_module:  # No selection → text-client fallback
        return False
    if game_module in _SKIP_GAME_VALIDATION_MODULES:
        return False
    if not game_label:
        return False
    return True


def _players_dir() -> str:
    """Settings-resolved Players directory (settings.generator.
    player_files_path) -- the dir Generate itself scans. `Utils.players_path`
    needs a beta core new enough to ship it; older cores fall back to the
    user_path default."""
    players_path = getattr(Utils, "players_path", None)
    if players_path is not None:
        return players_path()
    return user_path("Players")


with open(os.path.join(os.path.dirname(__file__), "launcher.kv"), encoding="utf-8") as kv_file:
    Builder.load_string(kv_file.read())

class LauncherLayout(MDNavigationLayout):
    pass

class LauncherView(MDBoxLayout):
    slot_layout: ObjectProperty
    server_layout: ObjectProperty
    title_layout: ObjectProperty
    fallback_status = StringProperty(_NO_GAME_STATUS)

class LauncherAuthTextField(MDTextField):
    pass

class LauncherGenerateContent(MDBoxLayout):
    pass

class LauncherHostContent(MDBoxLayout):
    """Start/Host dialog body: a segmented Local Host / Upload switch over a
    fixed-height section box, so the dialog never resizes after opening."""
    mode = StringProperty("local")

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self._local_widgets = [self.ids.port, self.ids.admin_password]
        self._upload_note = MDLabel(
            text="Host on multiworld.gg instead: the upload page opens in "
                 "your browser, where you upload the generated game (.zip) "
                 "and get a room to share.",
            theme_text_color="Custom",
            text_color=self.theme_cls.onSurfaceVariantColor,
            size_hint_x=0.8,
            pos_hint={"center_x": 0.5},
        )

    def set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        box = self.ids.mode_box
        box.clear_widgets()
        if mode == "local":
            for widget in self._local_widgets:
                box.add_widget(widget)
        else:
            box.add_widget(self._upload_note)

class LauncherPatchContent(MDBoxLayout):
    pass

@dataclass(frozen=True)
class YamlComponent: #TODO: AAAAAAAAAAA noooo it was supposed to be a component in LauncherComponents not added here
    """Synthetic strip entry for the YAML creator.

    Not a world-declared component: it applies to whichever game is selected,
    so it's appended to every selected game's strip instead of coming from the
    manifest scan. Duck-types WorldTool where the strip reads it."""
    module: str
    name: str = "Create YAML"
    type: str = "yaml"
    description: str = ""


@dataclass(frozen=True)
class SetupGuideComponent:
    """Synthetic strip entry for the selected game's setup guide, appended
    alongside YamlComponent and read by the strip the same way."""
    module: str
    name: str = "Setup Guide"
    type: str = "setup"
    description: str = ""


class LauncherComponentButton(MDButton):
    text = ""
    icon = "wrench"

    def __init__(self, **kwargs):
        self.text = kwargs.pop("text", "")
        self.icon = kwargs.pop("icon", "wrench")
        super().__init__(**kwargs)

class LauncherNavDrawerButton(MDNavigationDrawerItem):
    """Nav drawer action item. Unlike a navigation item it tracks no
    selection, and it puts the drawer away on release so the drawer isn't
    left hanging under whatever dialog the action opens."""
    icon = StringProperty("")
    text = StringProperty("")
    trailing_text = StringProperty("")

    def on_release(self, *args):
        # Runs after any bound action callbacks (default handlers dispatch
        # last), replacing MDNavigationDrawerItem's selection bookkeeping.
        widget = self.parent
        while widget is not None and not isinstance(widget, MDNavigationDrawer):
            widget = widget.parent
        if widget is not None:
            widget.set_state("close")

class LauncherScreen(MDScreen, ThemableBehavior):
    '''
    This is the main screen for the launcher.
    Left side has the game list/sorter
    Right contains the previously selected game
    with options to connect to the MW server
    '''
    name = "launcher"
    launchergrid: LauncherLayout
    nav_drawer: MDNavigationDrawer
    nav_menu: NavDrawerMenu
    important_appbar: MDSliverAppbar
    launcher_view: LauncherView
    game_filter: list
    available_games: list
    game_tag_filter: StringProperty
    bottom_appbar: BottomAppBar
    selected_game: tuple[str, str] = ("", "")
    # "game" = the selected game's client (text client when none selected); the
    # radio checkboxes override with "text"/"universal_tracker"/"manual".
    client_type: str = "game"
    highlighted_favorite: ObjectProperty(None, allownone=True)
    app: MDApp
    result: Any
    favorite_games: ListProperty = ListProperty([])
    saved_games: ListProperty = ListProperty([])
    _password_as_text: bool = False  # raw vs masked password in server_address

    # Launch button label/icon per client_type, see update_connect_ok_text.
    _CLIENT_TYPE_LABELS = {
        "game": ("Launch & Play", "rocket-launch"),
        "text": ("Launch Text Client", "console-line"),
        "universal_tracker": ("Launch Tracker", "map-marker-radius"),
        "manual": ("Launch Manual Client", "book-open-variant"),
    }

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.game_filter = []
        self.games_mdlist = MDList(width=260)
        self.game_tag_filter = "popular"
        self.selected_game = ""
        self.highlighted_favorite = None
        self.app = MDApp.get_running_app()
        self.available_games = []
        # None until the first manifest scan lands (module -> WorldTool list).
        self._world_components: dict[str, list] | None = None
        # Modules explicitly installed into custom_worlds/ (Install APWorld),
        # captured by the same scan.
        self._custom_world_modules: set[str] = set()
        self._component_buttons: list[LauncherComponentButton] = []
        # Python-built nav drawer widgets (everything below the static
        # Host/Generate/Patch items), replaced wholesale on each rebuild.
        self._drawer_widgets: list = []

        # Built only for its .text_input (app._create_screen reaches in), never
        # attached to the tree -- "Launch & Play" covers the bar's one action
        # and the chat FAB has no command processor on this screen.
        self.bottom_appbar = BottomAppBar(screen_name="launcher")
        self.important_appbar = LauncherSliverAppbar()
        self.launcher_view = LauncherView()
        Clock.schedule_once(lambda x: self.init_important())

    def show_snackbar(self, message: str, is_error: bool = False):
        """Show a snackbar notification"""
        snackbar = MDSnackbar(
            MDSnackbarText(
                text=message,
            ),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            md_bg_color=self.app.theme_cls.errorColor if is_error else self.app.theme_cls.primaryColor,
        )
        snackbar.open()

    def init_important(self):
        """Initialize the bigger parts of the launcher screen"""
        self.launchergrid = LauncherLayout()

        self.add_widget(self.launchergrid)

        self.important_appbar.size_hint_x = 260/Window.width
        self.important_appbar.size_hint_y=1
        self.launcher_view.size_hint_x = 1-(264/Window.width)
        self.launcher_view.size_hint_y =1

        self.important_appbar.ids.scroll.scroll_wheel_distance = 40
        #self.important_appbar.ids.scroll.y = 82

        self.important_appbar.content.add_widget(self.games_mdlist)

        # MDNavigationLayout accepts only the screen manager and the drawer, so
        # the launcher UI lands on the content screen inside the manager; the
        # drawer slides over it all (sliver appbar included) as a modal overlay.
        content_screen = self.launchergrid.ids.launcher_content
        content_screen.add_widget(self.important_appbar)
        self.launcher_view.pos_hint={"y": 0, "x": 260/Window.width}
        content_screen.add_widget(self.launcher_view)

        self.nav_drawer = self.launchergrid.ids.launcher_nav_drawer
        self.nav_menu = self.launchergrid.ids.launcher_nav_menu
        # One frame late so the menu width fix reads a laid-out width.
        Clock.schedule_once(lambda dt: self.nav_menu.on_start())
        self._rebuild_nav_drawer_menu()

        fave_scroll = FavoritesScroll()
        self.favorites_layout = fave_scroll.favorites
        self.launcher_view.ids.title_layout.add_widget(fave_scroll)
        fave_scroll.size = (self.launcher_view.ids.title_layout.width, dp(100))
        
        self.available_games = get_available_worlds()
        self.load_favorite_games()
        self.launcher_view.bind(fallback_status=self.on_fallback_status_changed)
        Clock.schedule_once(lambda dt: self.update_connect_button_text(), 0.2)
        #Clock.schedule_once(lambda dt: self.update_selected_game(), 0.2)
        Clock.schedule_once(lambda dt: self.populate_favorites(), 0.2)
        # Start game list population after available_games is populated
        asynckivy.start(self.set_game_list())
        # Warm the per-game component cache so the first game selection
        # usually finds it already loaded.
        self.refresh_world_components()

    def on_fallback_status_changed(self, instance, value):
        """Update the padding of the launcher view based on the fallback status"""
        if value:
            self.launcher_view.padding = dp(50), dp(10), dp(50), dp(50)
        else:
            self.launcher_view.padding = dp(50)

    async def set_game_list(self):
        """Set the game list based on the game tag filter"""
        matching_games = GameIndex.search(self.game_tag_filter)
        not_in_available_games = [game_module for game_module in matching_games.keys() \
                                  if game_module not in self.available_games]
        for game_module in not_in_available_games:
            matching_games.pop(game_module)
        self.games_mdlist.clear_widgets()
        for module_name, game_data in matching_games.items():
            await asynckivy.sleep(0)
            game = GameListPanel(
                item_name=module_name, 
                item_data=game_data,
                on_game_select=lambda x, name=module_name, game_name=game_data['game_name']: self.on_game_selected((name, game_name))
            )
            self.games_mdlist.add_widget(game)

    def on_game_selected(self, game_info: tuple[str, str]):
        """Handle game selection from the game list or favorites bar;
        selecting the already-selected game deselects it."""
        if self.selected_game and game_info[0] == self.selected_game[0]:
            self.deselect_game()
            return
        self.selected_game = game_info
        self.launcher_view.fallback_status = ""
        logger.info(f"Selected game: {game_info[1]}")
        self.launcher_view.module_name = game_info[0]
        self._update_component_strip()
        self.add_to_favorite_bar(game_info[0])
        self._highlight_favorite(game_info[0])

    def deselect_game(self):
        """Return to the no-selection state (see _NO_GAME_STATUS: the backend
        falls back to the generic Archipelago text client)."""
        self.selected_game = ""
        self.launcher_view.fallback_status = _NO_GAME_STATUS
        self.launcher_view.module_name = ""
        self.set_favorite_highlight(None)
        self._update_component_strip()

    def _highlight_favorite(self, module_name: str):
        """Highlight the favorites-bar tile for `module_name`, if present."""
        for widget in self.favorites_layout.children:
            if isinstance(widget, Favorite) and widget.game_module == module_name:
                self.set_favorite_highlight(widget)
                return
        self.set_favorite_highlight(None)

    def apply_game_search(self, query: str):
        """Repopulate the game list for `query`; an empty query falls back to
        the "popular" set (the same default the launcher starts with)."""
        self.game_tag_filter = (query or "").strip() or "popular"
        asynckivy.start(self.set_game_list())

    def set_filter(self, active, tag):
        """Set the game search filter based on the game tag filter"""
        if active:
            self.game_filter.append((self.game_tag_filter.text, tag))
        else:
            self.game_filter.remove((self.game_tag_filter.text, tag))

    def on_game_tag_filter_text(self, instance):
        """Set the game search filter based on the game tag filter"""
        self.game_filter = [(self.game_tag_filter.text, tag) for tag in GameIndex.search(self.game_tag_filter.text)]

    def update_connect_button_text(self):
        """Update the launch button label/icon to match the selected client type."""
        connect_button = self.launcher_view.ids.connect_button
        text, icon = self._CLIENT_TYPE_LABELS.get(self.client_type, self._CLIENT_TYPE_LABELS["game"])
        if self.client_type == "game":
            client = self._selected_game_client()
            if client is not None:
                text = client.name
        connect_button._button_text.text = text
        connect_button._button_icon.icon = icon

    def _selected_game_client(self) -> Any | None:
        """The selected world's declared client component, or None."""
        module = self.selected_game[0] if self.selected_game else ""
        if not module:
            return None
        for component in (self._world_components or {}).get(module, []):
            if getattr(component, "type", "") == "client":
                return component
        return None

    def set_client_type(self, client_type: str):
        """Set the client type"""
        self.client_type = client_type
        self.update_connect_button_text()

    def load_favorite_games(self):
        """Load favorite games from app config"""
        try:
            favorites_str = self.app.app_config.get('game_settings', 'favorite_games', fallback='')
            if favorites_str:
                self.saved_games = favorites_str.split(',')
                self.favorite_games = self.saved_games.copy()
            else:
                self.saved_games = []
                self.favorite_games = []
        except (KeyError):
            self.favorite_games = []
            self.saved_games = []
        logger.debug(f"Loaded {len(self.favorite_games)} favorite games")

#####################FAVORITES#############################

    def save_favorite_games(self, module_name: str = None):
        """Save favorite games to app config"""
        try:
            if module_name:
                self.saved_games.append(module_name)
            if not self.app.app_config.has_section('game_settings'):
                self.app.app_config.add_section('game_settings')
            self.app.app_config.set('game_settings', 'favorite_games', ','.join(self.saved_games).lstrip(","))
            self.app.app_config.write()
            logger.debug(f"Saved {len(self.favorite_games)} favorite games")
        except Exception as e:
            logger.error(f"Failed to save favorite games: {e}")

    def populate_favorites(self, game_module: str = None):
        """Populate the favorites with favorite games"""
        try:
            self.favorites_layout.clear_widgets()
            
            if not self.favorite_games and not game_module:
                # Add a placeholder item when no favorites
                placeholder = Favorite(game_name="", game_module="")
                self.favorites_layout.add_widget(placeholder)
                return
            
            for name in self.favorite_games:

                try:
                    game_name = GameIndex.get_game_name_for_module(name)
                    if game_name:
                        favorite_tab = Favorite(game_name=game_name, game_module=name)
                        self.favorites_layout.add_widget(favorite_tab)
                        if game_module and game_module == name:
                            self.set_favorite_highlight(favorite_tab)
                except Exception as e:
                    logger.error(f"Failed to add favorite {name}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to populate favorites tabs: {e}")

    def add_to_favorite_bar(self, module_name: str):
        """Add a game to favorites"""
        if module_name not in self.favorite_games:
            self.favorite_games.append(module_name)
            self.populate_favorites(module_name)

    def remove_from_favorites(self, module_name: str):
        """Remove a game from favorites"""
        if module_name in self.saved_games:
            self.saved_games.remove(module_name)
            self.save_favorite_games()
            self.populate_favorites()
            logger.info(f"Removed {module_name} from favorites")

    def toggle_favorite(self, module_name: str):
        """Toggle favorite status for a game"""
        if module_name in self.saved_games:
            self.remove_from_favorites(module_name)
        else:
            self.save_favorite_games(module_name)

    def swipe_to_favorite(self, module_name: str):
        """Switch to a specific favorite game tab"""
        try:
            if not self.favorite_games:
                return
                
            # Find the game name for this module
            game_name = GameIndex.get_game_name_for_module(module_name)
            if game_name:
                self.favorites_layout.switch_tab(text=game_name)
                logger.info(f"Switched to favorite {module_name}")
            else:
                logger.warning(f"Game {module_name} not found in favorites")
                
        except Exception as e:
            logger.error(f"Failed to switch to favorite: {e}")

    def on_favorite_clicked(self, module_name: str):
        """Handle clicking on a favorite item in the tabs"""
        try:
            game_data = GameIndex.get_game(module_name)
            if game_data:
                game_name = game_data.get('game_name', module_name)
                self.on_game_selected((module_name, game_name))
                logger.info(f"Selected favorite game: {game_name}")
        except Exception as e:
            logger.error(f"Failed to select favorite game {module_name}: {e}")
    
    def set_favorite_highlight(self, favorite_widget):
        """Set which favorite is highlighted, unhighlighting the previous one"""
        # Unhighlight the previously highlighted favorite
        if self.highlighted_favorite and self.highlighted_favorite != favorite_widget:
            self.highlighted_favorite.unhighlight()
        
        # Set and highlight the new favorite
        self.highlighted_favorite = favorite_widget
        if favorite_widget:
            favorite_widget.highlight()

############### TOOL FUNCTIONS ###################

    def generate(self):
        """Generate a new game"""
        # Step 1: Select files (multiple .zip/.yaml files)
        selected_files = self._select_generation_files()
        if not selected_files:
            return
        
        # Step 2: Create temporary directory and process files
        temp_dir = self._create_temp_workspace(selected_files)
        if not temp_dir:
            return
            
        # Store temp_dir for later use
        self._generation_temp_dir = temp_dir
            
        # Step 3: Show generation options dialog
        self._show_generation_options()

    def _select_generation_files(self):
        """Select multiple .zip/.yaml files for generation"""
        # Show file dialog for .zip and .yaml files
        result = FileUtils.open_file_input_dialog(
            title="Select Generation Files (.zip/.yaml)",
            filetypes=[("YAML Files", ["*.yaml", "*.yml"]), ("ZIP Files", ["*.zip"]), ("All Supported", ["*.yaml", "*.yml", "*.zip"])],
            multiple=True,
            suggest=_players_dir()
        )
        
        if not result:
            return []
            
        # Handle both single file and multiple files
        if isinstance(result, str):
            selected_files = [result]
        else:
            selected_files = result
            
        # Show confirmation of selected files
        if len(selected_files) == 1:
            self.show_snackbar(f"Selected: {os.path.basename(selected_files[0])}")
        else:
            self.show_snackbar(f"Selected {len(selected_files)} files for generation")
            
        return selected_files

    def _create_temp_workspace(self, selected_files):
        """Create temporary directory and copy/extract files"""
        temp_dir = tempfile.mkdtemp(prefix="mwgg_generate_")
        
        for file_path in selected_files:
            if file_path.lower().endswith('.zip'):
                # Extract zip file
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            else:
                # Copy yaml file
                shutil.copy2(file_path, temp_dir)
        
        return temp_dir

    def _show_generation_options(self):
        """Show dialog with generation options"""
        # Create dialog content
        content = LauncherGenerateContent()
        seed_field = content.ids.seed
        output_field = content.ids.output
        
        # Create dialog
        dialog = MDDialog(
            MDDialogHeadlineText(
                text="Generation Options",
            ),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: self._on_generation_options_cancel(dialog)
                ),
                MDButton(
                    MDButtonText(text="Generate"),
                    on_release=lambda x: self._on_generation_options_confirm(dialog, seed_field, output_field)
                ),
                spacing=dp(8),
                pos_hint={"center_x": 0.5}
            )
        )
        
        # Store dialog reference and open it
        self._generation_dialog = dialog
        self._generation_result = None
        dialog.open()

    def _on_generation_options_cancel(self, dialog):
        """Handle generation options cancellation"""
        dialog.dismiss()
        # Cleanup temp directory
        self._cleanup_temp_dir(self._generation_temp_dir)
        delattr(self, '_generation_temp_dir')

    def _on_generation_options_confirm(self, dialog, seed_field, output_field):
        """Handle generation options confirmation"""
        try:
            seed = seed_field.text.strip()
            seed_value = int(seed) if seed else None
        except ValueError:
            self.show_snackbar("Seed must be a number or empty for random", is_error=True)
            return
            
        # Blank output -> omit --outputpath so Generate's settings-backed
        # default applies instead of an `output` dir under the launcher's cwd.
        output_path = output_field.text.strip()

        self._generation_result = {
            'seed': seed_value,
            'output_path': output_path
        }
        
        dialog.dismiss()
        # Continue with generation
        self._continue_generation()

    def _continue_generation(self):
        """Continue with generation after options are confirmed"""
        if not hasattr(self, '_generation_result') or not self._generation_result:
            self._cleanup_temp_dir(self._generation_temp_dir)
            return
            
        # Cleanup happens in the background thread after completion.
        self._execute_generation(self._generation_temp_dir, self._generation_result)

    def _execute_generation(self, temp_dir, options):
        """Execute the Generate component with options in a background thread"""
        from BaseUtils import is_frozen
        from LauncherComponents import find_component, get_exe

        # base_cmd: [exe] frozen, [sys.executable, script] from source; resolved
        # via LauncherComponents so it can't drift from the built exe name.
        base_cmd = get_exe(find_component("Generate"))
        cmd = [*base_cmd, "--player-files-path", temp_dir]
        cwd = os.path.dirname(base_cmd[-1])
        # PYTHONIOENCODING keeps the child's piped output UTF-8 regardless of
        # locale; SKIP_REQUIREMENTS_UPDATE stops the child re-running the world
        # updater the launcher already ran on cold start. KIVY_NO_ARGS disables
        # Kivy's argument parser when running from source.
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'SKIP_REQUIREMENTS_UPDATE': '1'}
        if not is_frozen():
            env['KIVY_NO_ARGS'] = '1'
        # Console-subsystem exe: suppress the window that would flash over the
        # GUI on frozen Windows (output streams to the logger regardless).
        popen_kwargs = {}
        if is_windows:
            popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

        if options.get('seed'):
            cmd.extend(["--seed", str(options['seed'])])
            
        if options.get('output_path'):
            cmd.extend(["--outputpath", options['output_path']])
        
        if not os.path.exists(temp_dir):
            logger.error(f"Temp directory {temp_dir} does not exist!")
            MessageBox("Generation Error", f"Temp directory does not exist: {temp_dir}").open()
            return
            
        logger.info(f"Starting generation with command: {' '.join(cmd)}")
        logger.info(f"Using temp directory: {temp_dir}")
        
        # Show loading screen
        Clock.schedule_once(lambda dt: self.app.loading_layout.show_loading(display_logs=True), 0)
        
        def run_generation():
            """Run generation in background thread and stream output to logger"""
            
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8',
                    errors='replace',
                    cwd=cwd,
                    bufsize=1,  # Line buffered
                    env=env,
                    **popen_kwargs
                )

                # Stream stdout
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        logger.info(f"[Generate] {line}")
                
                # Wait for process to complete
                process.wait()
                
                # Capture any remaining stderr
                stderr = process.stderr.read()
                if stderr:
                    for line in stderr.splitlines():
                        if line.strip():
                            logger.error(f"[Generate Error] {line}")
                
                # Hide loading screen and schedule UI update on main thread
                def show_success_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Generation Complete", 
                               "Game generation completed successfully!").open()
                    # Cleanup after success
                    self._cleanup_temp_dir(temp_dir)
                    if hasattr(self, '_generation_temp_dir'):
                        delattr(self, '_generation_temp_dir')
                    if hasattr(self, '_generation_result'):
                        delattr(self, '_generation_result')
                
                def show_failure_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Generation Failed", 
                               f"Generation failed with code {process.returncode}:\n{error_msg}").open()
                    # Cleanup after failure
                    self._cleanup_temp_dir(temp_dir)
                    if hasattr(self, '_generation_temp_dir'):
                        delattr(self, '_generation_temp_dir')
                    if hasattr(self, '_generation_result'):
                        delattr(self, '_generation_result')

                def show_restart_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Restart Required",
                               "You will need to restart the launcher to apply updates.",
                               is_error=True,
                               callback=lambda x: self.restart_launcher()).open()


                if process.returncode == 0:
                    Clock.schedule_once(show_success_dialog, 0)
                    logger.info("Generation completed successfully")
                elif process.returncode == 10:
                    # Exit code 10 means "wrong environment" - library updates needed
                    logger.info("Generation requested launcher restart for environment refresh")
                    Clock.schedule_once(show_restart_dialog, 0)
                else:
                    error_msg = stderr if stderr else "Unknown error"
                    Clock.schedule_once(show_failure_dialog, 0)
                    logger.error(f"Generation failed with return code {process.returncode}")
                    
            except Exception as e:
                logger.exception(f"Failed to execute generation: {e}")
                def show_error_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Generation Error", 
                               f"Failed to execute generation: {str(e)}").open()
                    # Cleanup after error
                    self._cleanup_temp_dir(temp_dir)
                    if hasattr(self, '_generation_temp_dir'):
                        delattr(self, '_generation_temp_dir')
                    if hasattr(self, '_generation_result'):
                        delattr(self, '_generation_result')
                Clock.schedule_once(show_error_dialog, 0)
        
        # Start generation in background thread
        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()

    def restart_launcher(self):
        """Restart the launcher with the same arguments (used after a
        Generate/Patch environment-refresh exit code)."""
        logger.info("Restarting launcher due to environment refresh...")

        # Frozen: sys.argv[0] IS the exe (== sys.executable) and would duplicate
        # as MultiWorld.py's launch_file positional -- strip it. Dev: argv[0] is
        # the script path python.exe still needs.
        restart_args = sys.argv[1:] if is_frozen() else sys.argv

        # Fully detach the child. `is_windows` is a bool (BaseUtils/Utils), not
        # a function -- calling it raises TypeError.
        if is_windows:
            subprocess.Popen([sys.executable] + restart_args,
                           cwd=os.getcwd(),
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([sys.executable] + restart_args,
                           cwd=os.getcwd(),
                           start_new_session=True)

        # Flush all logging handlers to ensure messages are displayed
        for handler in logging.root.handlers:
            handler.flush()

        # Use sys.exit to bypass cleanup and immediately terminate
        sys.exit(10)

    def _cleanup_temp_dir(self, temp_dir):
        """Clean up temporary directory"""
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

    def host(self):
        """Start/Host a game: locally via MultiServer, or on multiworld.gg"""
        self._show_host_options()

    def _show_host_options(self):
        """Show the Start/Host dialog: Local Host server options, or the
        multiworld.gg upload route"""
        content = LauncherHostContent()
        port_field = content.ids.port
        admin_password_field = content.ids.admin_password

        confirm_text = MDButtonText(text="Start Local Server")
        content.bind(mode=lambda _content, mode: setattr(
            confirm_text, "text",
            "Start Local Server" if mode == "local" else "Open Browser"))

        dialog = MDDialog(
            MDDialogHeadlineText(
                text="Start/Host Game",
            ),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: dialog.dismiss()
                ),
                MDButton(
                    confirm_text,
                    on_release=lambda x: self._on_host_options_confirm(dialog, content, port_field, admin_password_field)
                ),
                spacing=dp(8)
            )
        )

        # Store dialog reference and open it
        self._host_dialog = dialog
        self._host_result = None
        dialog.open()

    def _on_host_options_confirm(self, dialog, content, port_field, admin_password_field):
        """Handle host options confirmation"""
        if content.mode == "upload":
            dialog.dismiss()
            # The browser session owns the uploaded seed, so the room lands on
            # the user's own multiworld.gg dashboard -- never upload from here.
            webbrowser.open("https://mw.prismativerse.com/play/host") # change to multiworld.gg when promoted
            return

        port = port_field.text.strip()
        admin_password = admin_password_field.text.strip()
        
        # Validate port
        if port:
            try:
                port_value = int(port)
                if not (1 <= port_value <= 65535):
                    self.show_snackbar("Port must be between 1 and 65535", is_error=True)
                    return
            except ValueError:
                self.show_snackbar("Port must be a number", is_error=True)
                return
        
        self._host_result = {
            'port': port if port else None,
            'admin-password': admin_password if admin_password else None
        }
        
        dialog.dismiss()
        # Continue with hosting
        self._execute_host(self._host_result)

    def _execute_host(self, options):
        """Execute the Host component with options - detached from client"""
        from LauncherComponents import find_component, get_exe

        base_cmd = get_exe(find_component("Host"))
        cmd = list(base_cmd)
        cwd = os.path.dirname(base_cmd[-1])
        env = None if is_frozen() else {**os.environ, 'KIVY_NO_ARGS': '1'}

        if options.get('port'):
            cmd.extend(["--port", str(options['port'])])
            
        if options.get('admin-password'):
            cmd.extend(["--admin-password", options['admin-password']])
        
        logger.info(f"Starting detached server with command: {' '.join(cmd)}")
        
        # Launch server - console app will spawn its own terminal
        try:
            subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env
            )
            MessageBox("Server Started", "MultiworldGG Server has been started in a new terminal window.").open()
            logger.info("Server launched successfully (detached)")
            if hasattr(self, '_host_result'):
                delattr(self, '_host_result')
        except Exception as e:
            logger.exception(f"Failed to start server: {e}")
            MessageBox("Server Error", f"Failed to start server: {str(e)}").open()
            if hasattr(self, '_host_result'):
                delattr(self, '_host_result')
    
    def patch_game(self):
        """Patch the selected game"""
        # Step 1: Select patch file (.apbp)
        selected_file = self._select_patch_file()
        if not selected_file:
            return
        
        # Store selected file
        self._patch_file = selected_file
        
        # Step 2: Show patch options dialog
        self._show_patch_options()

    def _select_patch_file(self):
        """Select .ap file for patching"""
        # Show file dialog for .ap files
        result = FileUtils.open_file_input_dialog(
            title="Select Patch File (.ap*)",
            filetypes=[("All Files", ["*.*"])],
            multiple=False,
            suggest=user_path("output")
        )
        
        if not result:
            return None
            
        # Show confirmation
        self.show_snackbar(f"Selected: {os.path.basename(result)}")
        return result

    def _show_patch_options(self):
        """Show dialog with patch options"""
        # Create dialog content
        content = LauncherPatchContent()
        output_field = content.ids.output
        
        # Create dialog
        dialog = MDDialog(
            MDDialogHeadlineText(
                text="Patch Options",
            ),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: self._on_patch_options_cancel(dialog)
                ),
                MDButton(
                    MDButtonText(text="Patch"),
                    on_release=lambda x: self._on_patch_options_confirm(dialog, output_field)
                ),
                spacing=dp(8),
                pos_hint={"center_x": 0.5}
            )
        )
        
        # Store dialog reference and open it
        self._patch_dialog = dialog
        self._patch_result = None
        dialog.open()

    def _on_patch_options_cancel(self, dialog):
        """Handle patch options cancellation"""
        dialog.dismiss()
        if hasattr(self, '_patch_file'):
            delattr(self, '_patch_file')

    def _on_patch_options_confirm(self, dialog, output_field):
        """Handle patch options confirmation"""
        output_path = output_field.text.strip()
        if not output_path:
            output_path = os.path.join(os.getcwd(), 'output')
        
        self._patch_result = {
            'output_path': output_path
        }
        
        dialog.dismiss()
        # Continue with patching
        self._execute_patch(self._patch_file, self._patch_result)

    def _execute_patch(self, patch_file, options):
        """Execute the Patch script with options in background thread.

        No LauncherComponents component wraps a standalone Patch exe (only
        "Open Patch", which routes through spawn_client), so the frozen name
        resolves directly against BaseUtils.FROZEN_TARGETS -- the single
        source of truth for built exe names.
        """
        from BaseUtils import FROZEN_TARGETS

        if is_frozen():
            suffix = ".exe" if is_windows else ""
            exe_path = local_path(f"{FROZEN_TARGETS['Patch']}{suffix}")
            cmd = [str(exe_path), patch_file]
            cwd = os.path.dirname(exe_path)
            env = os.environ.copy()
        else:
            exe_path = Path(sys.executable)
            file_path = Path(local_path("Patch.py"))
            cmd = [str(exe_path), str(file_path), patch_file]
            cwd = os.path.dirname(file_path)
            # Also set KIVY_NO_ARGS to disable Kivy's argument parser
            env = os.environ.copy()
            env['KIVY_NO_ARGS'] = '1'
        # Same UTF-8 and no-child-update contract as the generation spawn.
        env['PYTHONIOENCODING'] = 'utf-8'
        env['SKIP_REQUIREMENTS_UPDATE'] = '1'

        if options.get('output_path'):
            cmd.extend(["--outputpath", options['output_path']])

        # Same console-window suppression as the generation flow: Patch is a
        # console-subsystem exe on frozen Windows.
        popen_kwargs = {}
        if is_windows:
            popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

        logger.info(f"Starting patch with command: {' '.join(cmd)}")
        
        # Show loading screen
        Clock.schedule_once(lambda dt: self.app.loading_layout.show_loading(display_logs=True), 0)
        
        def run_patch():
            """Run patch in background thread and stream output to logger"""
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8',
                    errors='replace',
                    cwd=cwd,
                    bufsize=1,  # Line buffered
                    env=env,
                    **popen_kwargs
                )

                # Stream stdout
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        logger.info(f"[Patch] {line}")
                
                # Wait for process to complete
                process.wait()
                
                # Capture any remaining stderr
                stderr = process.stderr.read()
                if stderr:
                    for line in stderr.splitlines():
                        if line.strip():
                            logger.error(f"[Patch Error] {line}")
                
                # Hide loading screen and schedule UI update on main thread
                def show_success_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Patch Complete", 
                               "Game patching completed successfully!").open()
                    if hasattr(self, '_patch_file'):
                        delattr(self, '_patch_file')
                    if hasattr(self, '_patch_result'):
                        delattr(self, '_patch_result')
                
                def show_failure_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    error_msg = stderr if stderr else "Unknown error"
                    MessageBox("Patch Failed", 
                               f"Patch failed with code {process.returncode}:\n{error_msg}").open()
                    if hasattr(self, '_patch_file'):
                        delattr(self, '_patch_file')
                    if hasattr(self, '_patch_result'):
                        delattr(self, '_patch_result')

                def show_restart_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Restart Required",
                               "You will need to restart the launcher to apply updates.",
                               is_error=True,
                               callback=lambda x: self.restart_launcher()).open()

                if process.returncode == 0:
                    Clock.schedule_once(show_success_dialog, 0)
                    logger.info("Patch completed successfully")
                elif process.returncode == 10:
                    # Exit code 10 means "wrong environment" - library updates needed
                    logger.info("Patch requested launcher restart for environment refresh")
                    Clock.schedule_once(show_restart_dialog, 0)
                else:
                    Clock.schedule_once(show_failure_dialog, 0)
                    logger.error(f"Patch failed with return code {process.returncode}")
                    
            except Exception as e:
                logger.exception(f"Failed to execute patch: {e}")
                def show_error_dialog(dt):
                    self.app.loading_layout.hide_loading()
                    MessageBox("Patch Error", 
                               f"Failed to execute patch: {str(e)}").open()
                    if hasattr(self, '_patch_file'):
                        delattr(self, '_patch_file')
                    if hasattr(self, '_patch_result'):
                        delattr(self, '_patch_result')
                Clock.schedule_once(show_error_dialog, 0)
        
        # Start patch in background thread
        thread = threading.Thread(target=run_patch, daemon=True)
        thread.start()
    
    def create_yaml(self):
        """Open the YAML creator screen for the selected game.

        The screen is lazy-created the first time the button is pressed
        (see MultiMDApp._create_screen), then re-entered on subsequent
        presses. It's torn down again in `on_connect` once a session is
        live, so each pre-connect session gets a fresh screen for the
        currently selected game.
        """
        if not self.selected_game:
            MessageBox("No Game Selected", "Please select a game before creating YAML.").open()
            return

        try:
            # If a yaml screen exists from a different game, drop it so
            # the new one is built for the current selection.
            existing = getattr(self.app, "yaml_screen", None)
            if existing is not None and getattr(existing, "selected_game", None) != self.selected_game:
                self.app.screen_manager.remove_widget(existing)
                self.app.yaml_screen = None
                self.app._invalidate_top_appbar_menu()

            if "yaml" not in self.app.screen_manager.screen_names:
                self.app._create_screen("yaml")
            self.app.screen_manager.current = "yaml"
        except Exception as e:
            logger.error(f"Failed to open YAML screen for {self.selected_game[1]}: {e}", exc_info=True, stack_info=True)
            MessageBox(
                "YAML Creation Error",
                f"Failed to open YAML editor for {self.selected_game[1]}: {str(e)}",
                is_error=True,
            ).open()

    def open_setup_guide(self):
        """Open the selected game's setup guide: a webhost page for an index
        game, and for an added (custom_worlds/) world the `docs/setup*.md` it
        ships, handed to the desktop's default handler.
        """
        if not self.selected_game:
            MessageBox("No Game Selected", "Please select a game before opening a setup guide.").open()
            return

        module, game_name = self.selected_game
        if module not in self._custom_world_modules:
            webbrowser.open(setup_guide_url(game_name))
            return

        try:
            doc_path = extract_bundled_setup_doc(module)
        except Exception as e:
            logger.error(f"Failed to extract the setup doc for {module}: {e}", exc_info=True)
            MessageBox("Setup Guide", f"Could not read the setup document: {e}", is_error=True).open()
            return

        if doc_path is None:
            MessageBox(
                "Setup Guide",
                "No setup document included, please ask the apworld owner for instructions.",
            ).open()
            return

        try:
            open_with_desktop(doc_path)
        except OSError as e:
            logger.error(f"Failed to open the setup doc for {module}: {e}", exc_info=True)
            MessageBox(
                "Setup Guide",
                f"Could not open the setup document. It is saved at:\n{doc_path}",
                is_error=True,
            ).open()

    # Play-page component strip: the selected game's manifest tools/adjusters,
    # run in-process behind the arbitrary-code warning. The declared client
    # names the Play button (update_connect_button_text), not a strip button.
    _COMPONENT_TYPE_ICONS = {"client": "play-network", "tool": "wrench", "adjuster": "tune", "yaml": "file-document-edit-outline", "setup": "book-open-page-variant"}

    def refresh_world_components(self):
        """One background manifest scan, cached per-module for the play strip.
        Import + scan on a worker thread; widgets touched only via Clock.
        Called at startup and again after an APWorld install."""
        def _load():
            try:
                import LauncherComponents as launcher_components
            except Exception:
                logger.exception("World component scan: core import failed")
                return
            # Claim the post-Install-APWorld refresh hook. Reclaimed on
            # every rescan, which is harmless.
            launcher_components._rebuild_launcher_ui = (
                lambda *a: Clock.schedule_once(self._on_apworld_installed))
            scan = getattr(launcher_components, "world_manifest_components", None)
            try:
                tools = scan() if scan is not None else []
            except Exception:
                logger.exception("World component scan failed")
                tools = []
            index: dict[str, list] = {}
            for tool in tools:
                index.setdefault(tool.module, []).append(tool)
            # Idempotent (the manifest scan already ran it); repeated here
            # only to learn WHICH modules are custom installs.
            register = getattr(Utils, "register_custom_worlds", None)
            try:
                custom_modules = set(register()) if register is not None else set()
            except Exception:
                logger.exception("Custom world scan failed")
                custom_modules = set()
            Clock.schedule_once(
                lambda dt: self._on_world_components_loaded(index, custom_modules))

        threading.Thread(target=_load, name="mwgg-world-components-scan", daemon=True).start()

    def _on_world_components_loaded(self, index: dict[str, list],
                                    custom_modules: set[str]):
        self._world_components = index
        self._custom_world_modules = custom_modules
        # Repaint for whatever is selected now -- a game picked before the
        # scan landed gets its strip filled in here.
        self._update_component_strip()
        self._rebuild_nav_drawer_menu()

    def _on_apworld_installed(self, *_args):
        """`LauncherComponents._rebuild_launcher_ui` hook, claimed by the
        scan worker: repaint everything an install changes.
        TODO: expose as a manual refresh too -- users can drop worlds into
        custom_worlds/ by hand and the launcher should catch up."""
        self.refresh_world_components()
        self.available_games = get_available_worlds()
        asynckivy.start(self.set_game_list())

    def _update_component_strip(self):
        view = self.launcher_view
        box = view.ids.game_components_box
        # Only the strip's own buttons are dynamic -- clear_widgets() here
        # would also wipe any static siblings sharing the row.
        for button in self._component_buttons:
            box.remove_widget(button)
        # selected_game is "" until the first selection despite the tuple
        # annotation -- never index it without the truthiness guard.
        module = self.selected_game[0] if self.selected_game else ""
        components = (self._world_components or {}).get(module, [])
        # The primary client names the Play button, so it gets no strip button
        # of its own; everything else a world declares does -- including a
        # second client such as a map tracker.
        primary_client = self._selected_game_client()
        tools = [c for c in components if c is not primary_client]
        # The YAML creator and the setup guide need a game, not a world
        # declaration, so every selected game gets both appended -- including
        # worlds that declare nothing at all.
        if module:
            tools.append(YamlComponent(module))
            tools.append(SetupGuideComponent(module))
        self._component_buttons = [self._make_component_button(tool) for tool in tools]
        for button in self._component_buttons:
            box.add_widget(button)
        self.update_connect_button_text()

    def _make_component_button(self, tool) -> LauncherComponentButton:
        button = LauncherComponentButton(icon=self._COMPONENT_TYPE_ICONS.get(tool.type, "wrench"),text=tool.name)
        button.bind(on_release=lambda *_args, t=tool: self._activate_world_component(t))
        return button

    def _activate_world_component(self, tool):
        component_type = getattr(tool, "type", "tool")
        if component_type == "yaml":
            self.create_yaml()
            return
        if component_type == "setup":
            self.open_setup_guide()
            return
        if component_type == "client":
            self._spawn_component_client(tool)
            return
        import LauncherComponents as launcher_components
        run_fn = getattr(launcher_components, "run_world_tool", None)
        if run_fn is None:
            MessageBox("World Tool", "This core version cannot run world tools.", is_error=True).open()
            return
        from mwgg_gui.launcher.launcher_components import world_tool_activator
        world_tool_activator(
            run_fn, tool, custom=tool.module in self._custom_world_modules)()

    def _spawn_component_client(self, tool):
        """Named-client twin of _spawn_client: same field reads, persist and
        health check; spawn_client stays the only spawn path. No pre-flight
        verify -- named components are often trackers/map clients whose game
        need not match the server slot. The client-type radios don't apply:
        a named component already picks which client to boot."""
        port_error = self._validate_port_input()
        if port_error:
            MessageBox("Invalid Port", port_error, is_error=True).open()
            return
        from BaseUtils import spawn_client

        host_port, slot_name, password = self._raw_connect_inputs()
        try:
            process = spawn_client(
                game=tool.module,
                server_address=host_port or None,
                slot_name=slot_name or None,
                password=password or None,
                client_type="game",
                component=tool.name,
            )
        except Exception as e:
            logger.error(f"Failed to launch {tool.name}: {e}")
            MessageBox("Launch Error", f"Failed to launch {tool.name}: {str(e)}", is_error=True).open()
            return
        self._persist_last_connect(host_port, slot_name)
        self._check_spawn_health(process, tool.name)

    # Nav drawer icons for builtin tool components, keyed by display name.
    # Anything core adds that isn't listed here falls back to a toolbox.
    _BUILTIN_DRAWER_ICONS = {
        "Open host.yaml": "file-cog",
        "Install APWorld": "package-down",
        "Export Datapackage": "database-export",
        "Build APWorlds": "package-variant",
    }

    def _rebuild_nav_drawer_menu(self):
        """Repaint everything below the drawer's static Host/Generate/Patch
        items: builtin tool components, tools from client-less worlds, and
        the Settings/Exit tail. Runs once at startup (tail only -- the tool
        sections need the manifest scan) and again on every scan repaint,
        including the post-Install-APWorld rescan."""
        menu = self.nav_menu
        for widget in self._drawer_widgets:
            menu.ids.menu.remove_widget(widget)
        self._drawer_widgets = []

        def _add(widget):
            self._drawer_widgets.append(widget)
            menu.add_widget(widget)

        # Core's Export Datapackage dumps only the worlds already loaded in
        # this process (the generic baseline); route it to the game-selection
        # dialog, which loads exactly the chosen worlds first.
        activate_overrides = {"Export Datapackage": self.export_datapackage}

        tool_entries = []
        if self._world_components is not None:
            # The scan worker already imported core LauncherComponents, so
            # building the builtin entries here is a sys.modules hit.
            from mwgg_gui.launcher.launcher_components import builtin_menu_entries
            try:
                tool_entries = builtin_menu_entries()
            except Exception:
                logger.exception("Nav drawer: builtin components unavailable")
        if tool_entries:
            _add(MDNavigationDrawerDivider())
            _add(NavDrawerLabel(text="Tools"))
            for entry in tool_entries:
                button = LauncherNavDrawerButton(
                    icon=self._BUILTIN_DRAWER_ICONS.get(entry.title, "toolbox-outline"),
                    text=entry.title)
                activate = activate_overrides.get(entry.title, entry.activate)
                button.bind(on_release=lambda *_a, activate=activate: activate())
                _add(button)

        installed_tools = self._installed_tools()
        if installed_tools:
            _add(MDNavigationDrawerDivider())
            _add(NavDrawerLabel(text="Installed Tools"))
            for tool in installed_tools:
                button = LauncherNavDrawerButton(
                    icon=self._COMPONENT_TYPE_ICONS.get(tool.type, "wrench"),
                    text=tool.name)
                button.bind(on_release=lambda *_a, t=tool: self._activate_world_component(t))
                _add(button)

        _add(MDNavigationDrawerDivider())
        settings_button = LauncherNavDrawerButton(icon="cog", text="Settings")
        settings_button.bind(on_release=lambda *_a: self.app.change_screen("settings"))
        _add(settings_button)
        exit_button = LauncherNavDrawerButton(icon="exit-to-app", text="Exit")
        exit_button.bind(on_release=lambda *_a: self.app.stop())
        _add(exit_button)

    def _installed_tools(self) -> list:
        """Tools/adjusters from explicitly installed (Install APWorld ->
        custom_worlds/) APWorlds that declare no client component. A world
        with a client surfaces its tools on the play strip when selected,
        and a bundled tool-only world stays off the drawer entirely --
        explicit installation is the opt-in for something that runs
        arbitrary code."""
        tools = []
        for module in sorted(self._custom_world_modules
                             & set(self._world_components or {})):
            components = self._world_components[module]
            if any(getattr(c, "type", "") == "client" for c in components):
                continue
            tools.extend(c for c in components
                         if getattr(c, "type", "") in ("tool", "adjuster"))
        return tools

    def export_datapackage(self):
        """Open the datapackage export dialog: pick any available games
        (customs included), then load exactly those worlds and export."""
        from mwgg_gui.launcher.export_datapackage import open_export_dialog
        open_export_dialog(self)

    def get_current_game(self) -> tuple[str, str] | None:
        """Return the currently selected (module_name, display_name) tuple,
        or None if nothing is selected. Used by the YAML creator package."""
        return self.selected_game or None

    @property
    def server_address(self) -> str:
        # Return the server address as a url parse string for connection.
        server_text = self.launcher_view.ids.server.text or self.launcher_view.ids.server.hint_text
        port_text = self.launcher_view.ids.port.text or self.launcher_view.ids.port.hint_text
        slot_name_text = self.launcher_view.ids.slot_name.text or self.launcher_view.ids.slot_name.hint_text
        if self._password_as_text:
            slot_password_text = self.launcher_view.ids.slot_password.text if self.launcher_view.ids.slot_password.text else ""
        else:
            slot_password_text = "********" if self.launcher_view.ids.slot_password.text else ""
        colon_text = ":" if slot_name_text else ""
        return f"{slot_name_text}{colon_text}{slot_password_text}@{server_text}:{port_text}" if server_text and port_text else None

    def _validate_port_input(self) -> str | None:
        """Return an error message if the port field is non-empty and not a
        valid 1-65535 integer, else None. An empty field is allowed (caller
        falls back to the hint-text default).
        """
        port_text = (self.launcher_view.ids.port.text or "").strip()
        if not port_text:
            return None
        try:
            port_value = int(port_text)
        except ValueError:
            return "Port must be a number."
        if not (1 <= port_value <= 65535):
            return "Port must be between 1 and 65535."
        return None

    def _raw_connect_inputs(self) -> tuple[str, str, str]:
        """Return (server_host_port, slot_name, raw_password) read directly from
        the launcher fields. Used by the pre-flight verifier so it doesn't have
        to unparse the masked `self.server_address` URL.
        """
        ids = self.launcher_view.ids
        server_text = ids.server.text or ids.server.hint_text or ""
        port_text = ids.port.text or ids.port.hint_text or ""
        slot_name = ids.slot_name.text or ids.slot_name.hint_text or ""
        password = ids.slot_password.text or ""
        host_port = f"{server_text}:{port_text}" if server_text and port_text else server_text
        return host_port, slot_name, password

    def _spawn_client(self, game_module: str, game_label: str) -> None:
        """Spawn a detached per-game client process and return to the idle
        launcher screen. `BaseUtils.spawn_client` owns exe
        resolution, argv flags, child env, and OS-level detachment -- the
        launcher only supplies the raw connect inputs, never builds argv
        itself. The pre-flight verify path and the skip path both funnel
        through here.
        """
        from BaseUtils import spawn_client

        host_port, slot_name, password = self._raw_connect_inputs()
        connect_button = self.launcher_view.ids.connect_button

        # MultiWorld.py's run_client only routes the no-game case when
        # client_type == "text" -- "game" with no module falls through every
        # routing branch and leaves the child stuck on a dead client GUI.
        # Universal Tracker / Manual with no game selected are a separate,
        # not-yet-defined no-game contract (Phase 2, monorepo-side).
        client_type = self.client_type
        if not game_module and client_type == "game":
            client_type = "text"

        try:
            process = spawn_client(
                game=game_module or None,
                server_address=host_port or None,
                slot_name=slot_name or None,
                password=password or None,
                client_type=client_type,
            )
        except Exception as e:
            logger.error(f"Failed to launch {game_label}: {e}")
            MessageBox("Launch Error", f"Failed to launch {game_label}: {str(e)}", is_error=True).open()
            return

        self._persist_last_connect(host_port, slot_name)

        connect_button.disabled = True
        self._check_spawn_health(process, game_label, on_settle=lambda: setattr(connect_button, "disabled", False))

    def spawn_text_client(self) -> None:
        """Tools-card entry point: spawn a Text Client independent of the
        Play tab's game selection/client-type radios."""
        from BaseUtils import spawn_client

        host_port, slot_name, password = self._raw_connect_inputs()

        try:
            process = spawn_client(
                server_address=host_port or None,
                slot_name=slot_name or None,
                password=password or None,
                client_type="text",
            )
        except Exception as e:
            logger.error(f"Failed to launch Text Client: {e}")
            MessageBox("Launch Error", f"Failed to launch Text Client: {str(e)}", is_error=True).open()
            return

        self._persist_last_connect(host_port, slot_name)
        self._check_spawn_health(process, "Text Client")

    def _check_spawn_health(self, process: subprocess.Popen, game_label: str, on_settle=None) -> None:
        """~3s after spawning, check whether the child exited immediately
        (bad exe path, import crash, etc.) and surface a MessageBox if so.
        `on_settle`, if given, always runs once the poll completes -- e.g.
        re-enabling the launch button regardless of outcome; the launcher
        never blocks on the spawned client's lifetime."""

        def _poll(dt):
            if on_settle is not None:
                on_settle()
            returncode = process.poll()
            if returncode is not None and returncode != 0:
                MessageBox(
                    "Launch Failed",
                    f"{game_label} exited immediately (code {returncode}). "
                    "Check the launcher log for details.",
                    is_error=True,
                ).open()

        Clock.schedule_once(_poll, 3)

    def _persist_last_connect(self, host_port: str, slot_name: str) -> None:
        """Persist last-used hostname/port/username for the next launcher
        session and for freshly-spawned clients' InitContext defaults; the
        spawned client is a separate process, so persist explicitly here."""
        host, _, port = host_port.rpartition(":") if host_port else ("", "", "")
        if host and port:
            persistent_store("client", "last_server_hostname", host)
            try:
                persistent_store("client", "last_server_port", int(port))
            except ValueError:
                pass
        if slot_name:
            persistent_store("client", "last_username", slot_name)

    def _verify_then_launch(self, game_module: str, game_label: str) -> None:
        """Pre-flight a Connect handshake against the server to confirm it
        expects `game_label` for the entered slot. On success, hand off to
        `_spawn_client`. On failure, show a modal error and stay on the
        launcher -- the user can correct their selection without losing the
        launcher entirely.

        The websocket handshake runs on a worker thread (its own asyncio loop)
        so the Kivy main thread stays responsive. The result is delivered
        back to the main thread via `Clock.schedule_once`.
        """
        host_port, slot_name, password = self._raw_connect_inputs()

        if not host_port:
            MessageBox("Connection Error",
                       "Please enter a valid server address and port.",
                       is_error=True).open()
            return
        if not slot_name:
            MessageBox("Connection Error",
                       "Please enter a slot name.",
                       is_error=True).open()
            return

        logger.info(f"Verifying slot {slot_name!r} expects game {game_label!r} on {host_port}")
        Clock.schedule_once(lambda dt: self.app.loading_layout.show_loading(display_logs=False), 0)

        def _worker():
            import asyncio
            try:
                result = asyncio.run(
                    verify_slot(host_port, slot_name, password or None, game_label)
                )
            except Exception as exc:
                logger.exception("verify_slot worker crashed")
                result = SlotVerifyResult(ok=False, transport_error=f"Verifier crashed: {exc}")
            Clock.schedule_once(
                lambda dt: self._handle_verify_result(
                    result, game_module, game_label, host_port, slot_name,
                ),
                0,
            )

        threading.Thread(target=_worker, name="mwgg-verify-slot", daemon=True).start()

    def _handle_verify_result(
        self,
        result: SlotVerifyResult,
        game_module: str,
        game_label: str,
        host_port: str,
        slot_name: str,
    ) -> None:
        """Kivy-main-thread handler for the pre-flight verifier's verdict."""
        self.app.loading_layout.hide_loading()

        if result.ok:
            logger.info(f"Slot verification passed for {slot_name!r} / {game_label!r}")
            self._spawn_client(game_module, game_label)
            return

        if "InvalidGame" in result.errors:
            MessageBox(
                "Wrong Game Selected",
                f"The server was not expecting {game_label} for {slot_name}, "
                f"please check to ensure you've selected the right game by "
                f"re-selecting it.",
                is_error=True,
            ).open()
            return
        if "InvalidSlot" in result.errors:
            MessageBox(
                "Unknown Slot",
                f"Server has no slot named '{slot_name}'.",
                is_error=True,
            ).open()
            return
        if "InvalidPassword" in result.errors:
            MessageBox(
                "Wrong Password",
                f"Wrong password for slot '{slot_name}'.",
                is_error=True,
            ).open()
            return
        if "IncompatibleVersion" in result.errors:
            MessageBox(
                "Incompatible Version",
                "Your client is incompatible with this server's required version.",
                is_error=True,
            ).open()
            return

        if result.transport_error:
            MessageBox(
                "Connection Failed",
                f"Could not reach {host_port}: {result.transport_error}",
                is_error=True,
            ).open()
            return

        error_summary = ", ".join(result.errors) if result.errors else "unknown error"
        MessageBox(
            "Connection Refused",
            f"The server refused the connection: {error_summary}",
            is_error=True,
        ).open()

    def connect(self):
        """Validate the launch settings and spawn the selected game's client
        as a separate process. The launcher never becomes a client itself --
        it always stays up and spawns; see `_spawn_client`."""
        logger.info("Connect method called!")

        port_error = self._validate_port_input()
        if port_error:
            MessageBox("Invalid Port", port_error, is_error=True).open()
            return

        game_module = self.selected_game[0] if self.selected_game else ""
        game_label = self.selected_game[1] if self.selected_game else "Text Client"

        if self.selected_game:
            self.app.logo_png = GameIndex.get_game(game_module).get("cover_url", None)
            logger.info(f"Attempting to launch module: {game_label}")
        else:
            logger.info("No game selected; falling back to Text Client.")

        # Masked logging only -- never used to build spawn argv, which reads
        # the raw fields via _raw_connect_inputs() instead.
        self._password_as_text = False
        logger.info(f"Server: {self.server_address}")

        if _needs_game_validation(game_module, game_label):
            self._verify_then_launch(game_module, game_label)
        else:
            logger.debug(
                "Skipping pre-flight game verification for module=%r (game-agnostic client).",
                game_module,
            )
            self._spawn_client(game_module, game_label)
