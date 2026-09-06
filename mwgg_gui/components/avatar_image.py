"""Avatar widgets that render through the trust gate and never show a broken image."""
from __future__ import annotations

from kivy.properties import StringProperty
from kivymd.uix.fitimage import FitImage
from kivymd.uix.list import MDListItemLeadingAvatar

from mwgg_gui.components.avatar_safety import (
    DEFAULT_AVATAR_SOURCE,
    avatar_source,
    mark_avatar_unavailable,
)

__all__ = ("AvatarFallbackBehavior", "AvatarFitImage", "AvatarLeadingAvatar")


class AvatarFallbackBehavior:
    """Mixin for AsyncImage widgets: set `avatar_url`, never `source`.

    Untrusted or empty URLs render the controller icon; a URL the loader
    fails on (404, offline) is swapped for the icon and cached as bad.
    """
    avatar_url = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.source = avatar_source(self.avatar_url)

    def on_avatar_url(self, _instance, url: str) -> None:
        self.source = avatar_source(url)

    def on_error(self, error) -> None:
        if self.source != DEFAULT_AVATAR_SOURCE:
            mark_avatar_unavailable(self.source)
            self.source = DEFAULT_AVATAR_SOURCE


class AvatarFitImage(AvatarFallbackBehavior, FitImage):
    pass


class AvatarLeadingAvatar(AvatarFallbackBehavior, MDListItemLeadingAvatar):
    pass
