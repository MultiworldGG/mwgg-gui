"""
LAUNCHER FAVORITE BAR

FavoritesScroll - horizontal scroller for favorite games, whole tiles only
FavoriteToggleButton - button for toggling a favorite game
Favorite - widget for displaying a favorite game
"""
from __future__ import annotations

__all__ = ('FavoritesScroll',
           'Favorite'
           )

import logging

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
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
                padding: dp(2),
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
    """The view is a whole number of tiles wide and a resting scroll glides
    onto a tile edge, so no tile shows cut off. Dragging a tile up pulls it
    out of the bar; right-clicking a tile un-favorites the game."""
    favorites: ObjectProperty
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scroll_type = ["content"]
        self.bar_width = dp(1)
        self.size_hint_x = None
        self.do_scroll_y = False
        # Tiles only see a still touch after this long, so a hesitant drag can still scroll or pull.
        self.scroll_timeout = 1000
        self.favorites = MDBoxLayout(orientation='horizontal', spacing=dp(10), adaptive_width=True, size_hint_y=None, height=dp(128))
        self.add_widget(self.favorites)
        self._pulled = None
        self._settle = Clock.create_trigger(self._settle_row)
        self.favorites.bind(width=self._settle)
        self.effect_x.bind(velocity=self._settle, is_manual=self._settle)

    def on_parent(self, _, parent):
        if parent:
            parent.bind(width=self._settle)

    def _settle_row(self, *_):
        if not self.favorites.children or not self.parent:
            return
        spacing = self.favorites.spacing
        pitch = self.favorites.children[0].width + spacing
        self.width = max(1, (self.parent.width + spacing) // pitch) * pitch - spacing
        span = self.favorites.width - self.width
        if span <= 0 or self.effect_x.is_manual or self.effect_x.velocity:
            return
        target = min(round(self.scroll_x * span / pitch) * pitch, span) / span
        if abs(target - self.scroll_x) > 1e-6:
            Animation.cancel_all(self, 'scroll_x')
            Animation(scroll_x=target, d=.15, t='out_quad').start(self)

    def on_scroll_start(self, touch, check_children=True):
        if not self._touch:
            # ScrollView's hand-off timer reads self._touch, so one left over from an earlier touch would fire on this one.
            Clock.unschedule(self._change_touch_mode)
        if 'button' in touch.profile and touch.button == 'right' and self.collide_point(*touch.pos):
            touch.ud[self._get_uid()] = {'mode': 'unfavorite'}
            tile = self._tile_at(touch.pos)
            if tile is not None:
                tile.unfavorite()
            return True
        return super().on_scroll_start(touch, check_children)

    def on_scroll_move(self, touch):
        # 'pull' and 'unfavorite' are modes ScrollView does not know, so it neither scrolls nor clicks for those touches.
        state = touch.ud.get(self._get_uid())
        if state and state['mode'] == 'unknown' and self._start_pull(touch):
            state['mode'] = 'pull'
        if state and state['mode'] == 'pull':
            self._pulled.pull(touch.y - touch.oy)
            return True
        return super().on_scroll_move(touch)

    def on_scroll_stop(self, touch, check_children=True):
        state = touch.ud.get(self._get_uid())
        if not (state and state['mode'] in ('pull', 'unfavorite')):
            return super().on_scroll_stop(touch, check_children)
        self._touch = None
        if state['mode'] == 'pull':
            self._pulled.release(touch.y - touch.oy)
            self._pulled = None
        return True

    def _tile_at(self, pos):
        x, y = self.to_local(*pos)
        return next((tile for tile in self.favorites.children if tile.collide_point(x, y)), None)

    def _start_pull(self, touch) -> bool:
        rise = touch.y - touch.oy
        if rise <= self.scroll_distance or rise <= abs(touch.x - touch.ox):
            return False
        self._pulled = self._tile_at((touch.ox, touch.oy))
        if self._pulled is None:
            return False
        self.effect_x.cancel()
        return True

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
        self._slot_y = None
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

    def unfavorite(self):
        self.app.launcher_screen.unfavorite(self.game_module)

    def pull(self, rise):
        """Lift the tile `rise` px above its slot, fading as it goes."""
        if self._slot_y is None:
            self._slot_y = self.y
        rise = max(rise, 0)
        self.y = self._slot_y + rise
        self.opacity = 1 - min(rise / self.height, 1)

    def release(self, rise):
        """Pulled past a third of its height the tile leaves the bar (the
        favorite stays saved); otherwise it drops back into its slot."""
        slot_y, self._slot_y = self._slot_y, None
        if rise > self.height / 3:
            anim = Animation(y=slot_y + self.height, opacity=0, d=.12)
            anim.bind(on_complete=lambda *_: self.app.launcher_screen.remove_from_favorite_bar(self.game_module))
        else:
            anim = Animation(y=slot_y, opacity=1, d=.15, t='out_quad')
        anim.start(self)

    def highlight(self):
        #self.img_pos = self.favorite_image.pos
        self.favorite_state = "selected"

    def unhighlight(self):
        #self.img_pos = self.favorite_image.pos
        self.favorite_state = "normal"