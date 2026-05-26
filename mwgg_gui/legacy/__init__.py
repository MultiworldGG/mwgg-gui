"""Legacy kvui shapes preserved for per-world clients.

The original ``kvui.py`` (still shipped as the entrypoint for world clients)
defined several widget classes that worlds like Universal Tracker and Manual
reference directly from their own ``Tracker.kv`` / ``Manual.kv`` rule sets.
The new ``mwgg_gui`` redesign doesn't need those classes for its own screens,
but cutting them entirely would break every world that already has a kv file
saying ``viewclass: 'SelectableLabel'`` or ``SelectableRecycleBoxLayout:``.

This module is the single source of truth for those classes. ``kvui.py``
re-exports them so the legacy import path (``from kvui import SelectableLabel``)
keeps working; per-world clients that opt into the new API can import directly
from ``mwgg_gui.legacy``.
"""
from __future__ import annotations

from .recycleview import (
    SelectableRecycleBoxLayout,
    SelectableLabel,
)

__all__ = (
    "SelectableRecycleBoxLayout",
    "SelectableLabel",
)
