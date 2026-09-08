"""
Team goal detection from the server's `_read_client_status_{team}_{slot}` keys.

Kivy-free on purpose: the GUI-side unit tests load it by file path.
"""
from __future__ import annotations

__all__ = ("client_status_keys", "team_goaled", "apply_client_status")

from collections.abc import Iterable, Mapping

from NetUtils import ClientStatus


def client_status_keys(team: int, slots: Iterable[int]) -> list[str]:
    """Status keys for every slot on `team`; slot 0 is the server itself."""
    return [f"_read_client_status_{team}_{slot}" for slot in slots if slot != 0]


def team_goaled(stored_data: Mapping[str, object], team: int, slots: Iterable[int]) -> bool:
    """True once every slot reads CLIENT_GOAL; non-player slots do from load."""
    keys = client_status_keys(team, slots)
    return bool(keys) and all(stored_data.get(key) == ClientStatus.CLIENT_GOAL for key in keys)


def apply_client_status(stored_data: Mapping[str, object], team: int,
                        players: Mapping[int, object]) -> set[int]:
    """Set game_status "GOAL" on every player whose key reads CLIENT_GOAL; returns the slots that changed."""
    changed = set()
    for slot, player in players.items():
        if stored_data.get(f"_read_client_status_{team}_{slot}") != ClientStatus.CLIENT_GOAL:
            continue
        try:
            if player.game_status == "GOAL":
                continue
            player.game_status = "GOAL"
        except AttributeError:
            # consume_players_package leaves bare dicts here until on_connect rebuilds them.
            continue
        changed.add(slot)
    return changed
