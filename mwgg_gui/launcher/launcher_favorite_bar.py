"""
LAUNCHER FAVORITE BAR

FavoritesScroll - horizontal scroller for favorite games
FavoriteToggleButton - button for toggling a favorite game
Favorite - widget for displaying a favorite game
"""
from __future__ import annotations

__all__ = ('FavoritesScroll',
           'Favorite'
           )

import logging

from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ColorProperty, ListProperty, ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.imagelist import MDSmartTile, MDSmartTileImage
from kivymd.uix.scrollview import MDScrollView

from mwgg_igdb import GameIndex

logger = logging.getLogger("Client")

Builder.load_string('''

<FavoriteToggleButton>:
    style: "standard"
    pos_hint:{"right": 1, "top": 1}
    theme_text_color: "Custom"
    text_color: app.theme_cls.onPrimaryColor

<Favorite>:
    size_hint_x: None
    size_hint_y: None
    width: dp(85)
    height: dp(128)
    pos_hint: {"center_y": 0.5}
    overlap: True
    favorite_image: favorite_image

    FavoriteImage:
        source: root.game_cover_url
        id: favorite_image


 
    MDSmartTileOverlayContainer:
        height: dp(128)
        orientation: 'vertical'
        overlay_mode: 'footer'
        game_label: game_label

        FavoriteToggleButton:
            icon: "heart" if root.game_module in app.launcher_screen.saved_games else "heart-outline"
            outline_color: app.theme_cls.onSurfaceVariantColor
            outline_width: 1
            adaptive_height: True
            padding: dp(2), dp(2), 0, 0
            on_release: root.toggle_favorite()
            pos_hint: {"y": 1, "right": 1}


        MDRelativeLayout:
            MDLabel:
                id: game_label
                pos_hint: {"x": 0, "y": 0}
                padding: 2,
                adaptive_height: True
                text: root.game_name
                halign: 'center'
                theme_font_style: "Custom"
                font_style: "Monospace-SM"
                role: "medium"
                bold: True
                outline_color: app.theme_cls.surfaceContainerHighestColor
                outline_width: 1
                theme_text_color: "Custom"
                text_color: app.theme_cls.onSurfaceVariantColor
                canvas.before:
                    # Not md_bg_color: MDLabel swaps it for a SmoothRoundedRectangle whose
                    # translucent anti-aliased edge ignores the ScrollView stencil.
                    Color:
                        rgba: 0, 0, 0, .6
                    Rectangle:
                        pos: self.pos
                        size: self.size

            Widget:
                canvas.after:
                    Color:
                        rgba: app.theme_cls.primaryColor if root.favorite_state == "selected" else app.theme_cls.transparentColor
                    BoxShadow:
                        inset: True
                        size: dp(85), dp(128)
                        offset: 0, 0
                        spread_radius: 5, 5
                        blur_radius: 10


''')


class FavoritesScroll(MDScrollView):
    favorites: ObjectProperty
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scroll_type = ["content"]
        self.bar_width = dp(1)
        self.favorites = MDBoxLayout(orientation='horizontal', spacing=dp(10), size_hint_x=None, size_hint_y=None, height=dp(128), width=dp(1000), pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self.favorites)

class FavoriteImage(MDSmartTileImage):
    pass

class FavoriteToggleButton(MDIconButton):

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        return False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            return super().on_touch_up(touch)
        return False

class Favorite(MDSmartTile):
    """Custom Layout for displaying favorite games"""
    game_module = StringProperty("")
    game_name = StringProperty("")
    label_bg_color = ColorProperty([0,0,0,0])
    click_down_pos = ListProperty([])
    app = ObjectProperty()
    favorite_image: ObjectProperty
    favorite_state = StringProperty("normal")
    img_pos = ListProperty([0,0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.favorite_state = "normal"
    @property
    def game_cover_url(self):
        """Get the cover URL for the game"""
        if not self.game_module:
            return ""
        try:
            game_data = GameIndex.get_game(self.game_module)
            if game_data:
                cover_url = game_data.get('cover_url',"")
                return cover_url.replace("t_thumb", "t_cover_small").replace(".jpg", ".png") 
            return ""
        except:
            return ""

    def on_touch_down(self, touch):
        self.click_down_pos = touch.pos
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.click_down_pos:
            if self.collide_point(*self.click_down_pos):
                # Highlight state is owned by the screen: selection highlights
                # the matching tile, reselecting toggles the game off again.
                self.app.launcher_screen.on_favorite_clicked(self.game_module)
            self.click_down_pos = []
            return super().on_touch_up(touch)

    def toggle_favorite(self):
        self.app.launcher_screen.toggle_favorite(self.game_module)

    def highlight(self):
        #self.img_pos = self.favorite_image.pos
        self.favorite_state = "selected"

    def unhighlight(self):
        #self.img_pos = self.favorite_image.pos
        self.favorite_state = "normal"