from __future__ import annotations

from .components import *
from .console import *
from .hint import *
from .launcher import *
from .settings import *
from .overrides import *

from .loadanimlayout import MWGGLoadingLayout

# Importing this module is a side effect: it patches Kivy's ImageLoader to
# recognize `ap:` and `ap:zip:` URL prefixes used by world client kvs
# (Universal Tracker, etc.). Lives under `overrides/` alongside the other
# kivy/kivymd extension points (screen, expansionlist, markuptextfield, ...).
from .overrides.imageloader import ApAsyncImage, register_url_scheme  # noqa: F401

from .constants import (
    CONSOLE_ACTIONS,
    LAUNCHER_ACTIONS,
)