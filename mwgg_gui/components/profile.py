from __future__ import annotations
"""
PROFILE DISPLAY

Widgets to display each part of the profile.

ProfileAvatar:
    Displays the avatar image and allows the user to select a new one.
    Also allows the user to remove the current avatar.
ProfileAlias:
    Displays the alias and allows the user to edit it.
ProfilePronouns:
    Displays the pronouns and allows the user to edit it.
ProfileBK:
    Displays a switch to enable/disable BK mode.
ProfileInCall:
    Displays a switch to enable/disable in call mode.
"""

__all__ = ("ProfileAvatar", 
           "ProfileAlias", 
           "ProfilePronouns", 
           "ProfileBK", 
           "ProfileInCall",
           "show_profile")
import logging
import os
import threading
from Utils import persistent_load
from Utils import persistent_store
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField, MDTextFieldHelperText, MDTextFieldHintText
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.app import MDApp
from kivy.properties import StringProperty, ObjectProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.behaviors import CircularRippleBehavior
from kivy.metrics import dp
from kivy.clock import Clock, mainthread
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.fitimage import FitImage
from kivymd.uix.dialog import (MDDialog,
                               MDDialogContentContainer,
                               MDDialogHeadlineText,
                               MDDialogSupportingText,
                               MDDialogButtonContainer)
from kivymd.uix.divider import MDDivider
from kivymd.uix.widget import Widget

from kivy.lang import Builder

from mwgg_gui.components.avatar_safety import (
    AvatarUploadError,
    mint_token,
    safe_avatar_source,
    upload_avatar,
)
from mwgg_gui.constants import AVATAR_FILE_EXTENSIONS
        
logger = logging.getLogger("MultiWorld")

KV = """
<ProfileField>:
    orientation: "horizontal"
    pos_hint: {"center_x": 0.5, "top": 1}
    size_hint_x: 0.8
    size_hint_y: None
    height: dp(80)
    padding: dp(4)
    spacing: dp(4)
    profile_input: profile_input
    profile_input_icon: profile_input_icon
    MDLabel:
        text: root.label
        size_hint_x: 0.3
    MDTextField:
        id: profile_input
        on_text_validate: root.save_profile_field(self.text)
        MDTextFieldLeadingIcon:
            id: profile_input_icon
        MDTextFieldHelperText:
            text: root.hint_text

<ProfileSwitch>:
    orientation: "horizontal"
    size_hint_x: 0.8
    size_hint_y: None
    pos_hint: {"center_x": 0.5}
    height: dp(55)
    padding: dp(4)
    spacing: dp(4)
    profile_switch: profile_switch
    MDLabel:
        text: root.label
        theme_text_color: "Primary"
        size_hint_x: 0.3
    MDSwitch:
        id: profile_switch
        on_active: root.save_profile_switch(self.active)
"""

Builder.load_string(KV)

class ProfileField(MDBoxLayout):
    """Profile field section"""
    label = StringProperty("")
    settings_name = StringProperty("")
    hint_text = StringProperty("")
    profile_input: ObjectProperty = None
    profile_input_icon: ObjectProperty = None
    icon: StringProperty = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.local_player_data = self.app.local_player_data
        self.profile_input = self.ids.profile_input
        self.profile_input_icon = self.ids.profile_input_icon
        self.icon = self.ids.profile_input_icon.icon
        self.profile_input.text = persistent_load().get('client', {}).get(self.settings_name, '')

    def save_profile_field(self, instance):
        """Save profile field to config"""
        if isinstance(instance, MDTextField):
            text = instance.text
        elif isinstance(instance, MDSwitch):
            text = instance.active
        persistent_store('client', self.settings_name, text)
        setattr(self.local_player_data, self.settings_name, text)

    @property
    def icon(self):
        return self.ids.profile_input_icon.icon
    
    @icon.setter
    def icon(self, value):
        self.ids.profile_input_icon.icon = value

class ProfileSwitch(MDBoxLayout):
    """Profile switch section"""
    label = StringProperty("")
    settings_name = StringProperty("")
    profile_switch: ObjectProperty = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.local_player_data = self.app.local_player_data
        self.profile_switch = self.ids.profile_switch

    def save_profile_switch(self, value: bool):
        """Save profile switch value"""
        setattr(self.local_player_data, self.settings_name, value)

class AvatarImage(CircularRippleBehavior, ButtonBehavior, FitImage):
    """Mixin for the avatar image"""
    def __init__(self, **kwargs):
        self.ripple_scale = 0.85
        super().__init__(**kwargs)
    
    def on_release(self):
        pass

class ProfileAvatar(MDBoxLayout):
    """Profile avatar section.

    The user picks a local image file; the client uploads it to the MWGG
    webhost and stores the server-issued trusted URL in _persistent_storage.yaml.
    Legacy or hostile URLs are silently dropped on render via safe_avatar_source.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.local_player_data = self.app.local_player_data
        self.adaptive_height = True
        self.size_hint_x = 0.6
        self.pos_hint = {"center_x": 0.5}
        self.orientation = "vertical"
        self.spacing = dp(8)

        stored_url = persistent_load().get('client', {}).get('avatar', '')
        # Avatar display (100x100 circular)
        self.avatar_display = AvatarImage(
            size_hint=(None, None),
            size=(dp(100), dp(100)),
            radius=[dp(50), dp(50), dp(50), dp(50)],  # Circular
            source=safe_avatar_source(stored_url),
            pos_hint={"center_x": 0.5}
        )
        self.choose_button = MDButton(
            MDButtonText(text="Choose image..."),
            style="filled",
            pos_hint={"center_x": 0.5},
        )
        self.choose_button.bind(on_release=lambda *_: self.open_file_chooser())
        self.status_label = MDLabel(
            text="",
            theme_text_color="Error",
            halign="center",
            size_hint_y=None,
            height=dp(24),
        )
        self.avatar_display.bind(on_release=lambda *_: self.open_file_chooser())
        self.add_widget(self.avatar_display)
        self.add_widget(self.choose_button)
        self.add_widget(self.status_label)

    def open_file_chooser(self):
        if getattr(self, "_uploading", False):
            return
        chooser = FileChooserIconView(
            filters=[lambda folder, name: name.lower().endswith(AVATAR_FILE_EXTENSIONS)],
        )
        layout = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8))
        layout.add_widget(chooser)
        button_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        cancel_btn = Button(text="Cancel")
        ok_btn = Button(text="Upload")
        button_row.add_widget(cancel_btn)
        button_row.add_widget(ok_btn)
        layout.add_widget(button_row)
        popup = Popup(title="Choose avatar image", content=layout, size_hint=(0.9, 0.9))

        def _on_cancel(*_):
            popup.dismiss()

        def _on_submit(*_):
            if not chooser.selection:
                return
            path = chooser.selection[0]
            popup.dismiss()
            self._begin_upload(path)

        cancel_btn.bind(on_release=_on_cancel)
        ok_btn.bind(on_release=_on_submit)
        chooser.bind(on_submit=lambda inst, sel, touch: _on_submit())
        popup.open()

    def _begin_upload(self, path: str):
        self._uploading = True
        self.choose_button.disabled = True
        self.status_label.theme_text_color = "Secondary"
        self.status_label.text = "Uploading..."
        threading.Thread(
            target=self._upload_worker, args=(path,), daemon=True
        ).start()

    def _upload_worker(self, path: str):
        try:
            token = persistent_load().get('client', {}).get('avatar_token', '')
            if not token:
                token = mint_token()
                persistent_store('client', 'avatar_token', token)
            try:
                url = upload_avatar(path, token)
            except AvatarUploadError as exc:
                # Token may have been revoked; mint a fresh one and retry once.
                msg = str(exc)
                if "401" in msg or "Token" in msg:
                    token = mint_token()
                    persistent_store('client', 'avatar_token', token)
                    url = upload_avatar(path, token)
                else:
                    raise
            self._finish_upload_success(url)
        except AvatarUploadError as exc:
            logger.warning("Avatar upload failed: %s", exc)
            self._finish_upload_failure(str(exc))
        except Exception as exc:
            logger.exception("Unexpected error during avatar upload")
            self._finish_upload_failure(f"Upload failed: {exc}")

    @mainthread
    def _finish_upload_success(self, url: str):
        self._uploading = False
        self.choose_button.disabled = False
        self.status_label.theme_text_color = "Secondary"
        self.status_label.text = "Avatar updated."
        self.avatar_display.source = url
        self.save_avatar(url)
        Clock.schedule_once(lambda *_: setattr(self.status_label, "text", ""), 4)

    @mainthread
    def _finish_upload_failure(self, message: str):
        self._uploading = False
        self.choose_button.disabled = False
        self.status_label.theme_text_color = "Error"
        self.status_label.text = message[:120]

    def save_avatar(self, avatar_path: str):
        """Save avatar path to config"""
        persistent_store('client', 'avatar', avatar_path)
        self.local_player_data.avatar = avatar_path

class ProfileAlias(ProfileField):
    """Profile alias section"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = "Alias"
        self.settings_name = self.label.lower()
        self.hint_text = "Enter your alias"
        self.icon = "rename"
        self.bind(on_text_validate=self.save_profile_field)

class ProfilePronouns(ProfileField):
    """Profile pronouns section"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = "Pronouns"
        self.settings_name = self.label.lower()
        self.hint_text = "Enter your pronouns"
        self.icon = "human-greeting-variant"
        self.bind(on_text_validate=self.save_profile_field)
        
class ProfileBK(ProfileSwitch):
    """Profile status section"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = "BK Mode"
        self.settings_name = "in_bk"
        self.icon = "fast-food"
        self.bind(on_text_validate=self.save_profile_switch)

class ProfileInCall(ProfileSwitch):
    """Profile status section"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = "In Call"
        self.settings_name = "deafened"
        self.icon = "phone"
        self.bind(on_text_validate=self.save_profile_switch)

class ProfileDialog(MDDialog):
    """Profile dialog, overriding some stupid stuff"""
    def add_widget(self, widget):
        if isinstance(widget, ProfileAvatar):
            self.ids.headline_container.add_widget(widget)
            return True
        else:
            super().add_widget(widget)
            return True
    def save_button_release(self):
        """Save button release
        This is so jank."""
        for widget in self.ids.content_container.children[0].children:
            if isinstance(widget, ProfileField):
                widget.save_profile_field(widget.profile_input)
            elif isinstance(widget, ProfileSwitch):
                widget.save_profile_switch(widget.profile_switch.active)
        self.dismiss()

def show_profile():
    """Show the profile dialog"""
    app = MDApp.get_running_app()
    app.profile_dialog = ProfileDialog(
        ProfileAvatar(), MDDialogHeadlineText(
            text=f"{app.local_player_data.slot_name}", size_hint_x=0.6
        ),
        # -----------------------Supporting text-----------------------
        MDDialogSupportingText(
            text=f"""{app.local_player_data.pronouns}
            {app.local_player_data.game}
            {app.local_player_data.game_status}""".replace("  ", ""),
        ),
        # -----------------------Custom content------------------------
        MDDialogContentContainer(
            MDDivider(),
            ProfileAlias(),
            ProfilePronouns(),
            MDDivider(),
            ProfileBK(),
            ProfileInCall(),
            orientation="vertical",
            pos_hint={"center_x": 0.5},
        ),
        # ---------------------Button container------------------------
        MDDialogButtonContainer(
            Widget(),
            MDButton(
                MDButtonText(text="Cancel"),
                style="text",
                on_release=lambda x: app.profile_dialog.dismiss(),
            ),
            MDButton(
                MDButtonText(text="Save"),
                style="text",
                on_release=lambda x: app.profile_dialog.save_button_release(),
            ),
            spacing="8dp",
        ),
        # -------------------------------------------------------------
        auto_dismiss=False,
    )
    app.profile_dialog.open()