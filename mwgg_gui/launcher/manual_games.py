"""Manual Client radio rules, Kivy-free.

Like the Text Client radio, Manual only picks which client boots: the game
list selection rides along as --game. A client process loads only its routed
world, so a game-less manual launch has nothing to connect with and is refused.
"""
from __future__ import annotations

__all__ = ("MANUAL_GAME_PREFIX", "PICK_MANUAL_GAME", "is_manual_game", "manual_launch_block")

MANUAL_GAME_PREFIX = "Manual_"

PICK_MANUAL_GAME = "Click on a Manual game to select it, then launch the Manual Client."


def is_manual_game(module: str, game_name: str) -> bool:
    """Manual worlds are Manual_<game>_<creator>; an unindexed apworld may only
    carry its lowercase module slug."""
    return game_name.startswith(MANUAL_GAME_PREFIX) or module.startswith(MANUAL_GAME_PREFIX.lower())


def manual_launch_block(selected_game: tuple[str, str] | str) -> str | None:
    """Why the Manual Client cannot launch with this game-list selection, or None."""
    if not selected_game:
        return PICK_MANUAL_GAME
    module, name = selected_game
    if not is_manual_game(module, name):
        return f"{name} is not a Manual game. Pick one from the game list or switch to Game Client."
    return None
