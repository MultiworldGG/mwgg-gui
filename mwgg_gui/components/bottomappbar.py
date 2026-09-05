"""
BottomAppBar class - each screen's bottom bar. The left side carries the
screen-navigation buttons (model in bottom_nav.py, repainted through
MultiMDApp.refresh_bottom_nav); the FAB on the right slides the screen's
text input (chat, hint search, admin command) up from the bar. Compact
Mode drops the FAB, centers the buttons, and docks the text input
permanently above the bar (see layout_mode.docked_input).
"""
from __future__ import annotations

__all__ = (
    "BottomAppBar",
    "BottomBarTextInput"
)
from kivymd.uix.appbar import MDBottomAppBar
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, BooleanProperty, ListProperty
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDIconButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivymd.uix.textfield import MDTextField
from kivymd.uix.menu import MDDropdownMenu
from mwgg_gui.components.admin_commands import (
    admin_say_line, available_admin_commands, complete_admin_command)
from mwgg_gui.components.bottom_nav import NavEntry, icon_is_image
from mwgg_gui.constants import TEXT_INPUT_ACTIONS

Builder.load_string('''
<BottomAppBar>:
    fab_icon: "chat-outline"
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.primaryContainerColor \
                    if app.theme_cls.theme_style == "Light" \
                    else app.theme_cls.onPrimaryColor
    MDFabBottomAppBarButton:
        id: console_text_input_fab
        icon: root.fab_icon
        on_release: root.on_bar_action(self)

<BottomBarTextInput>:
    id: text_input
    -height: dp(56)
    hint_text: "Enter text"
    write_tab: False
    leading_icon: leading_icon
    MDTextFieldLeadingIcon:
        id: leading_icon
    MDTextFieldHintText:
        text: root.hint_text

<BottomNavBox>:
    orientation: "horizontal"
    adaptive_width: True
    size_hint: None, None
    height: dp(48)
    spacing: dp(4)
    x: dp(16)
    pos_hint: {"center_y": 0.5}

<BottomNavIconButton>:
    theme_icon_color: "Custom"
    icon_color: app.theme_cls.onSecondaryContainerColor if root.selected else app.theme_cls.onPrimaryContainerColor
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.secondaryContainerColor if root.selected else \
                 app.theme_cls.primaryContainerColor if app.theme_cls.theme_style == "Dark" else app.theme_cls.onPrimaryColor
    pos_hint: {"center_y": 0.5}

<BottomNavImageButton>:
    canvas.after:
        Color:
            rgba: 1, 1, 1, 1
        Rectangle:
            group: "nav-image"
            source: root.image_source
            size: root.image_size
            pos: self.center_x - root.image_size[0] / 2, self.center_y - root.image_size[1] / 2

<BottomNavTextButton>:
    style: "text"
    theme_bg_color: "Custom"
    md_bg_color: app.theme_cls.secondaryContainerColor if root.selected else \
                 app.theme_cls.primaryContainerColor if app.theme_cls.theme_style == "Dark" else app.theme_cls.onPrimaryColor
    pos_hint: {"center_y": 0.5}
    MDButtonText:
        text: root.nav_label
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSecondaryContainerColor if root.selected else app.theme_cls.onPrimaryContainerColor 
''')

def is_command_input(string: str) -> bool:
    return len(string) > 0 and string[0] in "/!"

class BottomBarTextInput(MDTextField):
    action_type: StringProperty
    leading_icon: ObjectProperty
    icon: StringProperty
    hint_text: StringProperty
    app: MDApp

    #hint autocomplete
    min_chars = NumericProperty(3)
    item_names: list[str] = []
    location_names: list[str] = []

    #BottomAppBar is a MDFloatLayout already, so we can place the TextField in it without shenanigans
    def __init__(self, *args, **kwargs):
        self.hint_text = ""
        self.action_type = "console"
        self.app = MDApp.get_running_app()
        super().__init__(*args, **kwargs)
        self.leading_icon = self.ids.leading_icon
        self.icon = "blank"
        self.dropdown = MDDropdownMenu(caller=self, position="top", border_margin=dp(2), width=self.width)
        self.bind(on_text_validate=self.on_fork)
        self.bind(width=lambda instance, x: setattr(self.dropdown, "width", x))
        self.write_tab = False

    def on_fork(self, instance):
        self.hint_text = ""
        self.dropdown.items.clear()
        if self.action_type == "hint":
            self.on_hint_search(instance.text)
        elif self.action_type == "admin":
            self.on_admin_message(instance.text)
        else:
            self.on_message(instance.text)
        self.text = ""

    @property
    def icon(self):
        return self.leading_icon.icon

    @icon.setter
    def icon(self, value):
        self.leading_icon.icon = value

    def on_admin_message(self, text):
        line = admin_say_line(text)
        if line.startswith("!admin login"):
            # Straight to the processor: on_message would echo the password
            # into the console and the up-arrow history.
            self.app.commandprocessor(line)
        else:
            self.app.on_message(line, self)

    def on_hint_search(self, text):
        if text in self.item_names:
            self.app.on_message("!hint "+text, self)
            self.item_names = []
            self.location_names = []
        elif text in self.location_names:
            self.app.on_message("!hint_location "+text, self)
            self.item_names = []
            self.location_names = []

    def on_message(self, text):
        self.app.on_message(text, self)

    def on_text(self, instance, value):
        if self.action_type == "admin":
            self.on_admin_input(instance, value)
        if self.action_type == "hint":
            self.on_hint_input(instance, value)
        else:
            return

    def on_admin_input(self, instance, value):
        """List the admin commands matching the bare word typed so far (Tab
        accepts the match); the dropdown closes once arguments follow."""
        self.dropdown.items.clear()
        ctx = self.app.ctx
        if not ctx.server:
            return
        word = value.strip().lstrip("/").lower()
        for command, usage in available_admin_commands(bool(ctx.admin)):
            if word and not command.startswith(word):
                continue
            self.dropdown.items.append({
                "text": command,
                "on_release": lambda cmd=(command, usage): self._select_admin_command(cmd),
            })
        if word and self.dropdown.items and not self.dropdown.parent:
            self.dropdown.open()
        elif not self.dropdown.items:
            self.dropdown.dismiss()

    def _select_admin_command(self, command):
        """Handle selection of an admin command from the dropdown"""
        self.text = f"{command[0]} "
        self.hint_text = command[1]
        self.dropdown.dismiss()
        Clock.schedule_once(lambda dt: self.do_cursor_movement("cursor_end"))

    def on_hint_input(self, instance, value):
        if len(value) >= self.min_chars:
            self.dropdown.items.clear()
            ctx = self.app.ctx
            if not ctx.game:
                return
            # TODO: Grab the flag, too to set the color in the dropdown
            self.item_names = [item for item in ctx.item_names._game_store[ctx.game].values()]
            self.location_names = [location for location in ctx.location_names._game_store[ctx.game].values()]

            def on_press(text):
                self.text = text
                self.dropdown.dismiss()
                self.focus = True

            lowered = value.lower()
            for hint_name in self.item_names + self.location_names:
                try:
                    index = hint_name.lower().index(lowered)
                except ValueError:
                    pass  # substring not found
                else:
                    # text = escape_markup(hint_name)
                    # text = text[:index]+text[index:index+len(value)]+text[index+len(value):]
                    self.dropdown.items.append({
                        "text": hint_name, #text to add markup
                        "on_release": lambda txt=hint_name: on_press(txt),
                        "leading_icon": "map-marker" if hint_name in self.location_names else "treasure-chest",
                        "markup": True
                    })
                    if len(self.dropdown.items) >= 10:
                        break
            if not self.dropdown.parent:
                self.dropdown.open()
            # else:
            #     Clock.schedule_once(self.dropdown.check_ver_growth, 0.1)
        else:
            self.dropdown.dismiss()

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        """
        Override the keyboard_on_key_down method to handle up and down arrow keys for history navigation
        """
        key, key_string = keycode

        if key == 9 and self.action_type == "admin":
            completed = complete_admin_command(self.text, bool(getattr(self.app.ctx, "admin", False)))
            if completed is not None:
                self.text = completed
                Clock.schedule_once(lambda dt: self.do_cursor_movement("cursor_end"))
            return True
        if key == 273 and key_string == 'up':
            self._change_to_history_text_if_available(self.app._command_history_index + 1)
            return True
        if key == 274 and key_string == 'down':
            self._change_to_history_text_if_available(self.app._command_history_index - 1)
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def _change_to_history_text_if_available(self, new_index: int) -> None:
        if new_index < -1:
            return
        if new_index >= len(self.app._command_history):
            return
        self.app._command_history_index = new_index
        if new_index == -1:
            self.text = ""
            return
        self.text = self.app._command_history[self.app._command_history_index]


class BottomNavButtonBehavior:
    """Nav-button surface shared by the icon and text variants."""
    screen = StringProperty("")
    nav_label = StringProperty("")
    selected = BooleanProperty(False)


class BottomNavIconButton(BottomNavButtonBehavior, MDIconButton):
    pass


class BottomNavImageButton(BottomNavIconButton):
    """Nav button drawing a world image (path or ap: URL) instead of a glyph.
    Drawn on the canvas: MDIcon accepts no child widgets besides a badge."""
    image_source = StringProperty("")
    image_size = ListProperty([dp(24), dp(24)])

    def on_image_source(self, _instance, source):
        try:
            width, height = CoreImage(source).texture.size
        except Exception:
            return
        scale = dp(24) / max(width, height, 1)
        self.image_size = [width * scale, height * scale]


class BottomNavTextButton(BottomNavButtonBehavior, MDButton):
    pass


class BottomNavBox(MDBoxLayout):
    pass


class BottomAppBar(MDBottomAppBar):
    text_input: BottomBarTextInput
    nav_box: BottomNavBox

    def __init__(self, screen_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = MDApp.get_running_app()
        self.screen_name = screen_name
        # Per-world tabs (CustomScreen) have no text input; their FAB stays inert.
        self.input_action = TEXT_INPUT_ACTIONS.get(screen_name)
        self.text_input = BottomBarTextInput(id=f'{screen_name}_text_input')
        self.ids.console_text_input_fab.id = "console_fab_button"
        if self.input_action:
            self.fab_icon = self.input_action["icon"]
        self.nav_box = BottomNavBox()
        self.add_widget(self.nav_box)
        self.docked = self.app.layout_mode.compact
        if self.docked:
            self._dock_layout()
        self.app.register_bottom_bar(self)

    def _dock_layout(self):
        self.remove_widget(self.ids.console_text_input_fab)
        self._fab_bottom_app_bar_button = None
        self.nav_box.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        if self.input_action is None:
            return
        self._configure_text_input()
        self.text_input.size_hint = (0.94, None)
        self.text_input.pos_hint = {"center_x": 0.5}
        self.text_input.y = self.height + dp(8)
        self.add_widget(self.text_input)

    def _configure_text_input(self):
        action = self.input_action
        self.text_input.icon = action["icon"]
        self.text_input.hint_text = action["label"]
        self.text_input.action_type = self.screen_name

    def add_widget(self, widget, index=0, canvas=None):
        # The text input and nav box position themselves; keep them out of
        # MDBottomAppBar's action-item layout.
        if isinstance(widget, (MDTextField, BottomNavBox)):
            MDFloatLayout.add_widget(self, widget, index, canvas)
        else:
            super().add_widget(widget, index, canvas)

    def rebuild_nav(self, entries: list[NavEntry], style: str, current: str) -> None:
        """Repaint the nav buttons; `style` is "icons" or "text"."""
        self.nav_box.clear_widgets()
        for entry in entries:
            if style == "text":
                button = BottomNavTextButton(screen=entry.name, nav_label=entry.label)
            elif icon_is_image(entry.icon):
                button = BottomNavImageButton(screen=entry.name, nav_label=entry.label,
                                              image_source=entry.icon)
            else:
                button = BottomNavIconButton(screen=entry.name, nav_label=entry.label,
                                             icon=entry.icon)
            button.bind(on_release=lambda _button, name=entry.name: self.app.change_screen(name))
            self.nav_box.add_widget(button)
        self.set_current(current)

    def set_current(self, screen_name: str) -> None:
        for button in self.nav_box.children:
            button.selected = button.screen == screen_name

    def on_bar_action(self, instance):
        if self.docked:
            return
        if self.text_input.parent and self.text_input.y > -50:
            self.hide_text_input()
        else:
            self.show_text_input()

    def show_text_input(self, prefill: str = ""):
        """Slide this screen's text input up from the bar and focus it."""
        if self.input_action is None:
            return
        if prefill:
            self.text_input.text = prefill
        if self.docked:
            self.text_input.focus = True
            return

        self._configure_text_input()
        if not self.text_input.parent:
            self.add_widget(self.text_input)

        self.text_input.y = -60
        self.text_input.pos_hint = {'center_x': 0.5, 'center_y': 0.5}
        self.text_input.size_hint = (0.4, None)

        def animate_in(dt):
            Animation(y=13, duration=0.2).start(self.text_input)

        Clock.schedule_once(animate_in, 0.1)
        self.text_input.focus = True

    def hide_text_input(self):
        """Hide the text input with animation"""
        if self.text_input.parent and not self.docked:
            def animate_out(dt):
                Animation(y=-60, duration=0.2).start(self.text_input)
                def remove_widget(dt2):
                    if self.text_input.parent:
                        self.remove_widget(self.text_input)
                Clock.schedule_once(remove_widget, 0.2)
            Clock.schedule_once(animate_out, 0.1)
