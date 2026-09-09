"""Manual Client radio rules (launcher/manual_games.py), loaded by file path
like the other Kivy-free launcher modules."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "launcher" / "manual_games.py"


@pytest.fixture(scope="module")
def manual_games():
    spec = importlib.util.spec_from_file_location("manual_games_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_manual_worlds_are_recognised_by_game_id_or_slug(manual_games):
    assert manual_games.is_manual_game("manual_autonauts_hopop", "Manual_Autonauts_Hopop")
    # Unindexed apworld: the launcher only knows the slug.
    assert manual_games.is_manual_game("manual_zelda_didi", "manual_zelda_didi")
    assert not manual_games.is_manual_game("khddd", "Kingdom Hearts Dream Drop Distance")


def test_manual_client_needs_a_manual_game_selected(manual_games):
    assert manual_games.manual_launch_block("") == manual_games.PICK_MANUAL_GAME
    assert manual_games.manual_launch_block(("manual_autonauts_hopop", "Manual_Autonauts_Hopop")) is None


def test_a_non_manual_selection_is_named_in_the_block(manual_games):
    block = manual_games.manual_launch_block(("khddd", "Kingdom Hearts Dream Drop Distance"))
    assert block.startswith("Kingdom Hearts Dream Drop Distance is not a Manual game")
