"""Kivy-free helpers for hint visibility on the classic table.

Hidden is client-owned and persisted: this client's ``hints_{team}_{slot}_mwgg``
entry carries ``MWGGUIHintStatus.HINT_HIDDEN`` next to the shop/goal/BK flags,
and ``UIHint.hide`` derives from it. The show-all switch is a view toggle: on
shows every hint for the slot, off drops found and hidden ones.
"""
from __future__ import annotations

import typing

HINT_HIDDEN = 0b1000  # NetUtils.MWGGUIHintStatus.HINT_HIDDEN


def is_hidden(status: int) -> bool:
    return bool(int(status) & HINT_HIDDEN)


def with_hidden(status: int, hidden: bool) -> int:
    status = int(status)
    return status | HINT_HIDDEN if hidden else status & ~HINT_HIDDEN


def row_visible(found: bool, hidden: bool, show_all: bool) -> bool:
    return show_all or not (found or hidden)


def resolve_ui_hint_bucket(hint: dict, slot_concerns_self: typing.Callable[[int], bool]) -> typing.Optional[int]:
    """The app.ui_hint_data bucket ("other player") holding this hint's UIHint,
    mirroring MultiMDApp.refresh_hints; None if neither side is this slot."""
    if slot_concerns_self(hint["receiving_player"]):
        return hint["finding_player"]
    if slot_concerns_self(hint["finding_player"]):
        return hint["receiving_player"]
    return None
