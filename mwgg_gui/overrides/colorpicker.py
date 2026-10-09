__all__ = ("MWColorPicker",)
from kivy.properties import AliasProperty, ColorProperty, StringProperty, ObjectProperty
from PIL import ImageGrab
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.textfield import MDTextFieldHintText
from kivymd.uix.fitimage import FitImage
from kivy.lang import Builder
from kivymd.theming import ThemableBehavior
from kivy.utils import get_hex_from_color, get_color_from_hex
from kivy.core.window import Window
from kivy.metrics import dp
import os
import re
import logging

logger = logging.getLogger("MultiWorld")

_HEX_PATTERN = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

KV = """
<ColorInfoLayout>:
    apply_color_button: apply_color_button
    revert_color_button: revert_color_button
    color_text: color_text
    cols: 2
    row_force_default: True
    row_default_height: dp(80)
    pos_hint: {"center_x": 0.5, "center_y": 0.5}
    spacing: dp(5)
    padding: 
    MDLabel:
        width: dp(60)
        size_hint_x: None
        text: "Color:"
        pos_hint: {"right": .9, "center_y": 0.5}
    BoxLayout:
        canvas.before:
            Color:
                rgba: root.theme_cls.surfaceContainerLowestColor
            RoundedRectangle:
                size: dp(160), dp(55)
                pos: self.pos
                radius: [dp(5)] * 4
        MDTextField:
            id: color_text
            size_hint_x: None
            width: dp(160)
            padding: dp(5)
            pos_hint: {"x": 0, "y": 0}
            theme_font_name: "Custom"
            font_name: app.theme_cls.font_styles.Monospace['large']['font-name'] 
            theme_font_size: "Custom"
            font_size: app.theme_cls.font_styles.Monospace['large']['font-size']
            theme_line_spacing: "Custom"
            line_spacing: app.theme_cls.font_styles.Monospace['large']['line-height']
            theme_text_color: "Custom"
            text_color_focus: root.color
            text_color_normal: root.color
            on_text_validate: root.on_text_field_change(self.text)
            keyboard_suggestions: False
            MDTextFieldLeadingIcon:
                theme_icon_color: "Custom"
                icon_color_normal: self.theme_cls.onSurfaceColor
                icon_color_focus: self.theme_cls.onSurfaceColor
                icon: "palette"
            ColorHintText:
                text_color_normal: root.old_color
                text_color_focus: root.old_color
                text: root.old_hex_color
                bold: True

    Widget:
        width: dp(60)
        size_hint_x: None
        canvas.before:
            Color:
                rgba: root.color
            RoundedRectangle:
                size: self.size
                pos: self.pos
                radius: [dp(10)] * 4
        size_hint: None, None
        size: dp(50), dp(50)
    MDBoxLayout:
        orientation: "horizontal"
        spacing: dp(5)
        padding: dp(5)
        pos_hint: {"center_x": 0.5, "center_y": 0.5}
        MDButton:
            id: apply_color_button
            pos_hint: {"center_x": 0.5, "center_y": 0.5}
            # on_press runs before the dialog's on_release dismiss.
            on_press: root.on_text_field_change(root.color_text.text)
            MDButtonText:
                theme_text_color: "Primary"
                text: "Apply"
        MDButton:
            id: revert_color_button
            pos_hint: {"center_x": 0.5, "center_y": 0.5}
            on_press: root.revert_color()
            MDButtonText:
                theme_text_color: "Primary"
                text: "Revert"

"""

# Load KV string once at module level
Builder.load_string(KV)

class ColorHintText(MDTextFieldHintText, ThemableBehavior):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_text_color = "Custom"
        self.text_color_focus = self.text_color_normal = self.text_color
        self.outline_color = self.theme_cls.onSurfaceColor
        self.outline_width = 1


class ColorInfoLayout(MDGridLayout, ThemableBehavior):
    color = ColorProperty([0, 0, 0, 0])
    old_color = ColorProperty([0, 0, 0, 0])
    old_hex_color = StringProperty("#000000")
    apply_color_button = ObjectProperty(None)
    revert_color_button = ObjectProperty(None)
    color_text = ObjectProperty(None)

    def __init__(self, old_hex_color, **kwargs):
        super().__init__(**kwargs)
        self.old_hex_color = old_hex_color
        self.old_color = get_color_from_hex(old_hex_color)

    def on_color(self, instance, value):
        self.color_text.text = get_hex_from_color(value)[:7]

    def on_text_field_change(self, text):
        """Show a typed #rgb or #rrggbb; anything else snaps the field back."""
        match = _HEX_PATTERN.fullmatch(text.strip())
        if match:
            digits = match.group(1)
            if len(digits) == 3:
                digits = "".join(c * 2 for c in digits)
            self.color = get_color_from_hex(digits)
        self.on_color(self, self.color)

    def revert_color(self, *args):
        self.color = self.old_color

class MWColorPicker(MDBoxLayout):
    orientation = "horizontal"
    color = ColorProperty([0, 0, 0, 0])
    hex_color = AliasProperty(lambda self: get_hex_from_color(self.color)[1:7], bind=("color",))

    def __init__(self, old_hex_color, **kwargs):
        logger.debug("Initializing MWColorPicker")
        super().__init__(**kwargs)
        self.old_hex_color = old_hex_color
        self.size_hint = (1, None)
        self.height = dp(250)  # Set a fixed height for the color picker
        
        # Create and configure the image. "scale-down" never draws past the
        # texture's 228 pixels (half size on Retina), so fix it at dp(228).
        self.image = FitImage(source=os.path.join(os.getenv("KIVY_DATA_DIR"), "images", "palette.png"),
                              fit_mode="contain", size_hint_y=None, height=dp(228), pos_hint={"center_y": .5})
        # Create and configure the info layout
        self.info_layout = ColorInfoLayout(old_hex_color=self.old_hex_color)
        
        self.add_widget(self.info_layout)
        self.add_widget(self.image)
        self.bind(color=self.info_layout.setter("color"))
        self.info_layout.bind(color=self.setter("color"))

    def on_touch_down(self, touch):
        try:
            # Check if touch is within the image's bounds
            if self.image.collide_point(touch.x, touch.y):

                # Convert touch position to window coordinates
                window_pos = self.to_window(touch.x, touch.y)
                
                # Window coordinates are GL pixels, but Window.left/top and the
                # screen grab use the OS's window units: points on macOS (two
                # pixels each on Retina), pixels on Windows and Linux.
                density = Window._density

                # Add window location offsets. Rounded because the macOS grab
                # (screencapture -R, then resize) only takes whole units.
                screen_x = round(Window.left + window_pos[0] / density)
                # Get the "inverse" position of the window because kivy is weird
                screen_y = round(Window.top + (Window.height - window_pos[1]) / density)
                
                # Get the color at the screen coordinates
                pixel = ImageGrab.grab(bbox=(screen_x, screen_y-1, screen_x+1, screen_y)).load()[0,0]
            
                # Convert to normalized color
                color = (pixel[0]/255, pixel[1]/255, pixel[2]/255, 1)
                
                # Update the color
                self.color = color
                return True
            elif self.info_layout.color_text.collide_point(touch.x, touch.y):
                super().on_touch_down(touch)
                return True
            elif self.info_layout.apply_color_button.collide_point(touch.x, touch.y):
                super().on_touch_down(touch)
                return True
            elif self.info_layout.revert_color_button.collide_point(touch.x, touch.y):
                super().on_touch_down(touch)
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Error in on_touch_down: {e}", exc_info=True)
            return False
