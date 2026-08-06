"""Hint-screen style resolution.

Deliberately import-light: the GUI-side unit tests load this module by
file path (bypassing mwgg_gui/__init__, which imports the full Kivy GUI),
so nothing heavy may be imported at module level. The new screen is the
``None`` sentinel rather than the HintScreen class because resolving it
here would import mwgg_gui.hint.hintscreen, whose module-level
``kivy.core.window`` import opens an SDL window under pytest — the caller
instantiates HintScreen itself on ``None``.
"""
from __future__ import annotations

import logging
import typing


def resolve_hint_screen_class(style: typing.Optional[str]) -> typing.Optional[type]:
    """Map a client.hint_screen config value to a hint screen class.

    "classic" resolves to the beta core's kvui.ClassicHintScreen when the
    installed core provides one. Everything else — any other value, an old
    core without the class, or a kvui that fails to import — returns
    ``None``, meaning "use the new HintScreen" (the cross-repo getattr
    degradation pattern).
    """
    normalized = (style or "").strip().lower()
    if normalized != "classic":
        return None
    try:
        import kvui
    except Exception as e:
        logging.getLogger("Client").warning(
            "Classic hint screen unavailable (kvui import failed: %s); "
            "using the new hint screen", e
        )
        return None
    cls = getattr(kvui, "ClassicHintScreen", None)
    if cls is None:
        logging.getLogger("Client").warning(
            "Classic hint screen unavailable in this MultiworldGG version; "
            "using the new hint screen"
        )
    return cls
