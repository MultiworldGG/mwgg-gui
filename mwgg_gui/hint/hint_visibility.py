"""Kivy-free helpers for the classic hint table's client-owned hidden flag.

Hidden lives in this client's ``hints_{team}_{slot}_mwgg`` datastore entry as
``MWGGUIHintStatus.HINT_HIDDEN`` next to the shop/goal/BK flags, so the console
sidebar and both hint screens read one state. Loaded by file path in tests.
"""
from __future__ import annotations

HINT_HIDDEN = 0b1000  # NetUtils.MWGGUIHintStatus.HINT_HIDDEN


def is_hidden(status: int) -> bool:
    return bool(int(status) & HINT_HIDDEN)


def with_hidden(status: int, hidden: bool) -> int:
    status = int(status)
    return status | HINT_HIDDEN if hidden else status & ~HINT_HIDDEN


def hidden_payload(keys, mwgg_hints: dict, hidden: bool) -> dict[str, int]:
    """One Set/update value flipping every key's hidden bit and keeping its other flags."""
    return {key: with_hidden(mwgg_hints.get(key) or 0, hidden) for key in keys}
