"""Admin command-line helpers (components/admin_commands.py).

Loaded by file path so the test never imports mwgg_gui (and thus Kivy).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "admin_commands.py"


@pytest.fixture(scope="module")
def admin_commands():
    spec = importlib.util.spec_from_file_location("admin_commands", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("typed, expected", [
    ("help", "!admin /help"),
    ("/help", "!admin /help"),
    ("//players", "!admin /players"),
    ("  send_location Alice Chest  ", "!admin /send_location Alice Chest"),
    ("!admin /send_location Alice Chest", "!admin /send_location Alice Chest"),
    ("!admin login hunter2", "!admin login hunter2"),
    ("login hunter2", "!admin login hunter2"),
    ("/login hunter2", "!admin login hunter2"),
    ("logout", "!admin logout"),
    ("", "!admin"),
])
def test_admin_say_line_never_doubles_the_slash(admin_commands, typed, expected):
    assert admin_commands.admin_say_line(typed) == expected


def test_only_login_is_offered_before_authenticating(admin_commands):
    before = [command for command, _ in admin_commands.available_admin_commands(False)]
    after = [command for command, _ in admin_commands.available_admin_commands(True)]
    assert before == ["login"]
    assert "login" not in after
    assert "logout" in after and "help" in after


@pytest.mark.parametrize("typed, logged_in, expected", [
    ("pl", True, "players "),
    ("/pl", True, "/players "),
    ("lo", False, "login "),
    ("lo", True, "logout "),
    ("hint_l", True, "hint_location"),
    ("h", True, None),
    ("zzz", True, None),
    ("", True, None),
    ("hint_location Alice", True, None),
])
def test_tab_completion(admin_commands, typed, logged_in, expected):
    assert admin_commands.complete_admin_command(typed, logged_in) == expected


def test_option_entries_start_from_room_info_and_take_the_payload_over_it(admin_commands):
    entries = admin_commands.option_entries(
        hint_cost=10, check_points=1,
        permissions={"release": "auto_enabled", "collect": "goal", "remaining": "disabled"})
    names = [entry["name"] for entry in entries]
    by_name = {entry["name"]: entry for entry in entries}
    assert names == [name for name, _ in admin_commands.OPTION_SPECS]
    assert names.index("hint_mode") == names.index("collect_mode") + 1
    assert not {"countdown_mode", "admin_password", "password"} & set(names)
    assert by_name["hint_cost"]["value"] == 10 and by_name["hint_cost"]["type"] == "int"
    assert by_name["release_mode"]["value"] == "auto_enabled"
    assert "auto" in by_name["release_mode"]["choices"]
    assert "auto" not in by_name["remaining_mode"]["choices"]
    assert by_name["hint_mode"]["choices"] == ("default", "own", "all")
    assert by_name["item_cheat"]["type"] == "bool" and by_name["item_cheat"]["value"] is None

    payload = [
        {"name": "hint_cost", "type": "int", "value": 25},
        {"name": "hint_mode", "type": "str", "value": "own", "choices": ["default", "own", "all"]},
        {"name": "countdown_mode", "type": "str", "value": "auto", "choices": ["enabled", "disabled", "auto"]},
        {"name": "password", "type": "str", "value": "********", "secret": True},
        {"name": "brand_new", "type": "bool", "value": True},
    ]
    entries = admin_commands.option_entries(payload, hint_cost=10)
    names = [entry["name"] for entry in entries]
    by_name = {entry["name"]: entry for entry in entries}
    assert by_name["hint_cost"]["value"] == 25
    assert by_name["hint_mode"]["value"] == "own"
    assert by_name["hint_mode"]["choices"] == ["default", "own", "all"]
    assert not {"countdown_mode", "password"} & set(names)
    assert entries[-1] == {"name": "brand_new", "type": "bool", "value": True, "choices": None}


STATUS_REPLY = """Player Status on team 0:
Bardic has 0 connections. (1/422)
DelPhillie has 0 connections and has finished. (349/349)
Flat Delilah has 2 connections 0 of which are tagged DeathLink and is ready. (14/250)
PhilliePuzzle has 1 connection 1 of which are tagged DeathLink. (15/254)"""


def test_parse_status_reply(admin_commands):
    parsed = admin_commands.parse_status_reply(STATUS_REPLY)
    assert parsed["team"] == 0 and parsed["tag"] == "DeathLink"
    players = parsed["players"]
    assert [p["name"] for p in players] == ["Bardic", "DelPhillie", "Flat Delilah", "PhilliePuzzle"]
    assert players[0] == {"name": "Bardic", "connections": 0, "tagged": 0, "checks": 1,
                          "total": 422, "state": None}
    assert players[1]["state"] == "goal" and players[2]["state"] == "ready"
    assert players[2]["connections"] == 2 and players[2]["tagged"] == 0
    assert players[3]["tagged"] == 1 and players[3]["checks"] == 15
    assert admin_commands.tagged_players(players) == 1


def test_parse_status_reply_without_tagged_clause_or_header(admin_commands):
    parsed = admin_commands.parse_status_reply(
        "Player Status on team 1:\nSolo has 0 connections. (0/9)")
    assert parsed == {"team": 1, "tag": None,
                      "players": [{"name": "Solo", "connections": 0, "tagged": 0, "checks": 0,
                                   "total": 9, "state": None}]}
    assert admin_commands.parse_status_reply("Set option hint_mode to own") is None
    assert admin_commands.parse_status_reply("") is None


def test_player_display_name(admin_commands):
    assert admin_commands.player_display_name({"name": "Alice", "alias": "Alice"}) == "Alice"
    assert admin_commands.player_display_name({"name": "Alice", "alias": "Al"}) == "Al (Alice)"
    assert admin_commands.player_display_name({"name": "Alice"}) == "Alice"


@pytest.mark.parametrize("row, expected", [
    ({"status": 30, "connected": False}, "goal"),
    ({"status": 30, "connected": True}, "goal"),
    ({"status": 10, "connected": False}, "ready"),
    ({"status": 20, "connected": True}, "connected"),
    ({"status": 5, "connected": True}, "connected"),
    ({"status": 0, "connected": False}, "disconnected"),
    ({"connected": True}, "connected"),
    ({}, "disconnected"),
])
def test_player_state_priority(admin_commands, row, expected):
    assert admin_commands.player_state(row) == expected


def test_state_icon_covers_every_state(admin_commands):
    icons = {admin_commands.state_icon(state)
             for state in ("goal", "ready", "connected", "disconnected")}
    assert len(icons) == 4
    assert admin_commands.state_icon("bogus") == "help-circle-outline"


class _Slot:
    def __init__(self, game):
        self.game = game


def test_enrich_player_rows_prefers_the_row_then_slot_then_name_match(admin_commands):
    slot_info = {1: _Slot("Game A"), 2: _Slot("Game B")}
    player_names = {1: "Alice", 2: "Bob (bob)"}
    rows = [
        {"name": "Alice", "slot": 1},
        {"name": "Bob (bob)"},
        {"name": "Already Known", "game": "Game C"},
        {"name": "Nobody"},
    ]
    enriched = admin_commands.enrich_player_rows(rows, slot_info, player_names)
    assert [row["game"] for row in enriched] == ["Game A", "Game B", "Game C", ""]


def test_session_time(admin_commands):
    assert admin_commands.format_session_time(0, 100.0) == ("Not started", "00:00:00")
    started, elapsed = admin_commands.format_session_time(1_000_000.0, 1_000_000.0 + 86400 + 61)
    assert elapsed == "1 day, 00:01:01"
    assert len(started) == 16
