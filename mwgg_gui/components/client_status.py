"""
Team goal detection from the server's `_read_client_status_{team}_{slot}` keys.

Kivy-free on purpose: the GUI-side unit tests load it by file path.
"""
from __future__ import annotations

__all__ = ("client_status_keys", "team_goaled")

from collections.abc import Iterable, Mapping

from NetUtils import ClientStatus


def client_status_keys(team: int, slots: Iterable[int]) -> list[str]:
    """Status keys for every slot on `team`; slot 0 is the server itself."""
    return [f"_read_client_status_{team}_{slot}" for slot in slots if slot != 0]


def team_goaled(stored_data: Mapping[str, object], team: int, slots: Iterable[int]) -> bool:
    """True once every slot reads CLIENT_GOAL; non-player slots do from load."""
    keys = client_status_keys(team, slots)
    return bool(keys) and all(stored_data.get(key) == ClientStatus.CLIENT_GOAL for key in keys)
