from __future__ import annotations
"""
MWGGLoadingLayout

Creates the loading animation within the application
that is displayed when the application is loading various
resources.
"""
__all__ = ("MWGGLoadingLayout",)

from kivy.properties import ListProperty, BooleanProperty, ObjectProperty, NumericProperty
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.image import Image
from kivy.lang import Builder
from PIL import Image as PILImage
from PIL import ImageSequence
import io
import os
import re
import logging
import tempfile
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.relativelayout import MDRelativeLayout
from kivy.app import App
from kivy.uix.effectwidget import PixelateEffect
from kivy.uix.textinput import TextInput

MIN_SPEED = 0.016  # Fastest speed (60fps)
MAX_SPEED = 0.050   # Slowest speed (20fps)
DEFAULT_SPEED = 0.040  # Default speed (40ms)

# Generate/Patch run as child processes; the launcher re-logs their stdout on
# "Client" under these prefixes, so their own logger names never carry records
# in this process.
LOG_SOURCE = "Client"
LOG_TAIL_LINES = 100
STREAM_PREFIXES = ("[Generate] ", "[Patch] ")
CHILD_LOG_STAMP = re.compile(r"^\d{2}:\d{2}:\d{2} \[[A-Z]+\]\s*")
# Not for users: scratch folders and the ROM prompt/path/checksum lines.
HIDDEN_LINE_PATTERNS = (
    re.compile(re.escape(tempfile.gettempdir()), re.IGNORECASE),
    re.compile(r"[\\/](?:tmp|temp)(?:[_\-.]\w*)?[\\/]", re.IGNORECASE),
    re.compile(r"\bROM\b"),  # upper-case only: "Loading base rom" stays
    re.compile(r"^Selected file:"),
    re.compile(r"^(?:CRC32|MD5|SHA-?\d*):"),
)


def display_text(message: str) -> str | None:
    """Return the user-facing form of a streamed child line, or None to hide it."""
    for prefix in STREAM_PREFIXES:
        if message.startswith(prefix):
            break
    else:
        return None
    text = CHILD_LOG_STAMP.sub("", message[len(prefix):]).rstrip()
    if not text.strip() or any(pattern.search(text) for pattern in HIDDEN_LINE_PATTERNS):
        return None
    return text


class CallbackHandler(logging.Handler):
    """Custom logging handler that calls a callback function for each log record."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            self.callback(record)
        except Exception:
            self.handleError(record)


class LoadingLogBox(TextInput):
    """Read-only tail of the Generate/Patch child output, shown under the animation."""

    def __init__(self, **kwargs):
        super().__init__(readonly=True, multiline=True, halign="left",
                         size_hint=(0.5, 0.2), pos_hint={"center_x": 0.5},
                         background_normal="", background_active="",
                         background_color=(0, 0, 0, 0), cursor_color=(0, 0, 0, 0),
                         **kwargs)
        self._tail: list[str] = []
        self._handler = CallbackHandler(self._on_record)
        self._handler.setLevel(logging.INFO)

    def attach(self):
        self._tail.clear()
        self.text = ""
        logging.getLogger(LOG_SOURCE).addHandler(self._handler)

    def detach(self):
        logging.getLogger(LOG_SOURCE).removeHandler(self._handler)

    def _on_record(self, record):
        text = display_text(record.getMessage())
        if text is None:
            return
        # Records arrive on worker threads; the widget is only touched on the Kivy thread.
        Clock.schedule_once(lambda dt: self._append(text), 0)

    def _append(self, message):
        self._tail.append(message)
        del self._tail[:-LOG_TAIL_LINES]
        self.text = "\n".join(self._tail)
        self.cursor = self.get_cursor_from_index(len(self.text))


img_path = os.path.join(os.getenv("KIVY_DATA_DIR"),"images", "loading_animation.png")

class MWGGLoadingLayout(MDRelativeLayout):
    frames = ListProperty([])
    img_box: MDBoxLayout
    loading = BooleanProperty(False)
    current_image: Image
    current_frame = NumericProperty(0)
    app = ObjectProperty(None)
    _clock_event = None
    log_box: LoadingLogBox

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = App.get_running_app()

        self.img_box = MDBoxLayout(theme_bg_color="Custom", md_bg_color=(0,0,0,0),
                                   pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                   size_hint=(None, None), size=(200, 200))
        img = PILImage.open(img_path)
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            new_frame = io.BytesIO()
            frame.save(new_frame,format="png", bitmap_format="png")
            new_frame.seek(0)  # Reset buffer position
            core_image = CoreImage(new_frame, ext='png', filename=f"frame_{i}.png")
            self.frames.append(Image(texture=core_image.texture))
        self.current_image = None
        self.current_frame = 0
        mono = self.app.theme_cls.font_styles["Monospace"]["small"]
        self.log_box = LoadingLogBox(foreground_color=self.app.theme_cls.onSurfaceColor,
                                     font_name=mono["font-name"], font_size=mono["font-size"])
        self.img_box.bind(pos=self._place_log_box, size=self._place_log_box)
        self.log_box.bind(size=self._place_log_box)

    def _place_log_box(self, *args):
        self.log_box.top = self.img_box.y - dp(12)

    def on_start(self):
        self.size = (self.app.root.width, self.app.root.height)
        self.pos_hint = {'center_x': 0.5, 'center_y': 0.5}

    def show_loading(self, display_logs=False, speed=DEFAULT_SPEED):
        # Guard against shutdown state where widgets might be None
        if self.img_box is None or self.app is None:
            return
            
        if not self.loading and not self.img_box.parent:
            self.loading = True
            self.add_widget(self.img_box)
            if display_logs:
                self.log_box.attach()
                self.add_widget(self.log_box)
            if hasattr(self.app, 'enable_effects'):
                self.app.enable_effects()
            else:
                self.app.pixelate_effect.effects = [PixelateEffect(pixel_size=3)]
            self._clock_event = Clock.schedule_interval(self.update_frame, speed)
    
    def set_speed(self, speed):
        """Set the animation speed. Speed should be between MIN_SPEED and MAX_SPEED."""
        if not self.loading:
            return
            
        speed = max(MIN_SPEED, min(MAX_SPEED, speed))
        
        if self._clock_event:
            self._clock_event.cancel()
        
        self._clock_event = Clock.schedule_interval(self.update_frame, speed)
    
    def update_frame(self, dt):
        if not self.loading or self.img_box is None:
            return False
        
        if self.current_image:
            self.img_box.remove_widget(self.current_image)
        
        self.current_image = self.frames[self.current_frame]
        self.img_box.add_widget(self.current_image)
        
        self.current_frame = (self.current_frame + 1) % len(self.frames)
    
    def hide_loading(self, *args):
        if self.loading:
            self.loading = False
            if self._clock_event:
                self._clock_event.cancel()
                self._clock_event = None
            if self.current_image and self.img_box is not None:
                self.img_box.remove_widget(self.current_image)
                self.current_image = None
            if self.log_box.parent:
                self.remove_widget(self.log_box)
            self.log_box.detach()
            if self.img_box is not None and self.img_box.parent:
                self.remove_widget(self.img_box)
            if hasattr(self.app, 'disable_effects'):
                self.app.disable_effects()
            else:
                self.app.pixelate_effect.effects = []  # Hide blur
