"""Team goal detection (components/client_status.py).

Loaded by file path so the test never imports mwgg_gui (and thus Kivy).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "client_status.py"
# NetUtils.ClientStatus.CLIENT_GOAL as the server JSON-encodes it.
GOAL = 30
SLOTS = {0: "Archipelago", 1: "Alice", 2: "Bob"}


@pytest.fixture(scope="module")
def client_status():
    pytest.importorskip(
        "NetUtils",
        reason="beta core not importable - set MWGG_BETA_SRC to the "
               "MultiworldGG/src checkout or run under the beta venv",
    )
    spec = importlib.util.spec_from_file_location("client_status", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_status_keys_skip_the_server_slot(client_status):
    assert client_status.client_status_keys(0, SLOTS) == [
        "_read_client_status_0_1", "_read_client_status_0_2"]


@pytest.mark.parametrize("stored_data, expected", [
    ({}, False),
    ({"_read_client_status_0_1": GOAL}, False),
    ({"_read_client_status_0_1": GOAL, "_read_client_status_0_2": 20}, False),
    ({"_read_client_status_0_1": GOAL, "_read_client_status_0_2": 0}, False),
    ({"_read_client_status_0_1": GOAL, "_read_client_status_0_2": GOAL}, True),
])
def test_team_goaled_needs_every_slot(client_status, stored_data, expected):
    assert client_status.team_goaled(stored_data, 0, SLOTS) is expected


def test_team_goaled_is_false_without_players(client_status):
    assert not client_status.team_goaled({}, 0, {0: "Archipelago"})


class _Player:
    def __init__(self, game_status="PLAYING"):
        self.game_status = game_status


def test_apply_marks_goaled_players_once(client_status):
    players = {1: _Player(), 2: _Player()}
    stored = {"_read_client_status_0_1": GOAL, "_read_client_status_0_2": 20}
    assert client_status.apply_client_status(stored, 0, players) == {1}
    assert players[1].game_status == "GOAL"
    assert players[2].game_status == "PLAYING"
    assert client_status.apply_client_status(stored, 0, players) == set()


def test_apply_reads_only_the_given_team(client_status):
    players = {1: _Player()}
    assert client_status.apply_client_status({"_read_client_status_1_1": GOAL}, 0, players) == set()
    assert players[1].game_status == "PLAYING"


def test_apply_skips_placeholder_entries(client_status):
    # consume_players_package resets ui_player_data values to bare dicts
    players = {1: {}, 2: _Player()}
    stored = {"_read_client_status_0_1": GOAL, "_read_client_status_0_2": GOAL}
    assert client_status.apply_client_status(stored, 0, players) == {2}
    assert players[1] == {}
