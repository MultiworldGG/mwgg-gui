"""
Backward-compatible shim: the canonical home for these dataclasses is now
`ui_dataclasses` in the MultiworldGG monorepo, so importing them doesn't
drag in Kivy via mwgg_gui's package __init__ chain.

In addition to the dataclasses themselves we re-export the NetUtils/BaseClasses
symbols that the old `guidataclasses.py` imported at module scope -- some
mwgg_gui modules (e.g. overrides/expansionlist.py) consume them from here
rather than from their original homes.
"""
from __future__ import annotations
__all__ = (
    "UIHint", "UIPlayerData", "MarkupPair",
    "Hint", "HintStatus", "MWGGUIHintStatus",
    "ItemClassification",
)

from ui_dataclasses import UIHint, UIPlayerData, MarkupPair
from NetUtils import Hint, HintStatus, MWGGUIHintStatus
from BaseClasses import ItemClassification
