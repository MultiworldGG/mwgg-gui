"""Routed-launch feedback policy (components/module_launch.py).

The module is Kivy-free and loaded by file path; BaseUtils and
subprocess.Popen are stubbed so the launcher spawn is checked without
starting a process.
"""
from __future__ import annotations

import configparser
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "module_launch.py"


@pytest.fixture(scope="module")
def module_launch():
    spec = importlib.util.spec_from_file_location("module_launch_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_patch_client_type_reads_the_settings_key(module_launch):
    config = configparser.ConfigParser()
    assert module_launch.read_patch_client_type(config) == "text"
    config.add_section("client")
    config.set("client", "patch_client_type", " Universal_Tracker ")
    assert module_launch.read_patch_client_type(config) == "universal_tracker"
    config.set("client", "patch_client_type", "manual")
    assert module_launch.read_patch_client_type(config) == "text"


def test_patch_client_labels_round_trip(module_launch):
    for value, label in module_launch.PATCH_CLIENT_LABELS.items():
        assert module_launch.patch_client_type_from_label(label) == value
    assert module_launch.patch_client_type_from_label("Bogus") == "text"


def test_patch_launch_announces_the_patch(module_launch):
    lines = module_launch.launch_status_lines(
        "papermario", patch_file="C:/Users/me/Downloads/MW_1_Player.appm64",
        server_address="host:38281")
    assert lines == ["Patching MW_1_Player.appm64..."]


def test_launch_without_a_patch_has_nothing_to_announce(module_launch):
    assert module_launch.launch_status_lines("papermario", server_address="host:38281") == []
    assert module_launch.launch_status_lines("papermario", patch_file=None) == []


def test_standalone_failure_offers_the_launcher_or_exit(module_launch):
    dialog = module_launch.launch_failure_dialog("Paper Mario", spawned_by_launcher=False)
    assert dialog.title == "Launch Failed"
    assert "Paper Mario" in dialog.message
    assert (dialog.ok_text, dialog.cancel_text) == ("Open Launcher", "Exit")
    assert dialog.opens_launcher


def test_launcher_spawned_failure_only_offers_exit(module_launch):
    dialog = module_launch.launch_failure_dialog("Paper Mario", spawned_by_launcher=True)
    assert (dialog.ok_text, dialog.cancel_text) == ("Exit", None)
    assert not dialog.opens_launcher


def test_launcher_env_drops_the_client_markers(module_launch):
    environ = {"MWGG_ROLE": "client", "MWGG_GAME": "papermario",
               "MWGG_CLIENT_TYPE": "game", "MWGG_SKIP_UPDATE": "1",
               "MWGG_FRONTEND": "gui", "PATH": "C:/bin"}
    assert module_launch.launcher_env(environ) == {"MWGG_FRONTEND": "gui", "PATH": "C:/bin"}


def test_spawn_launcher_runs_the_client_exe_detached(module_launch, monkeypatch):
    base_utils = types.ModuleType("BaseUtils")
    base_utils.get_client_exe = lambda: ["C:/apps/MultiworldGG.exe"]
    base_utils._detached_popen_kwargs = lambda: {"start_new_session": True}
    monkeypatch.setitem(sys.modules, "BaseUtils", base_utils)
    monkeypatch.setenv("MWGG_ROLE", "client")
    monkeypatch.setenv("MWGG_GAME", "papermario")
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return "popen"

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert module_launch.spawn_launcher() == "popen"
    (argv, kwargs), = calls
    assert argv == ["C:/apps/MultiworldGG.exe"]
    assert kwargs["start_new_session"] is True
    assert "MWGG_ROLE" not in kwargs["env"]
    assert "MWGG_GAME" not in kwargs["env"]


@pytest.fixture
def drop_core(monkeypatch):
    """Stub the core lookups dropped_patch_route uses: patch manifests by path, an
    index by game name, and custom worlds that only register on a rescan."""
    state = {"manifests": {}, "index": {"Paper Mario": "papermario"}, "custom": {}, "rescans": 0}

    def register_custom_worlds():
        state["rescans"] += 1
        state["index"].update(state["custom"])

    utils = types.ModuleType("Utils")
    utils.read_patch_game_name = state["manifests"].get
    utils.register_custom_worlds = register_custom_worlds
    igdb = types.ModuleType("mwgg_igdb")
    igdb.GameIndex = types.SimpleNamespace(get_module_for_game=lambda game: state["index"].get(game))
    monkeypatch.setitem(sys.modules, "Utils", utils)
    monkeypatch.setitem(sys.modules, "mwgg_igdb", igdb)
    return state


def test_dropped_non_patch_has_no_route(module_launch, drop_core):
    assert module_launch.dropped_patch_route("C:/Downloads/notes.txt") == (None, None)
    assert drop_core["rescans"] == 0


def test_dropped_patch_routes_by_manifest_not_suffix(module_launch, drop_core):
    drop_core["manifests"]["C:/Downloads/MW_P1.unregistered"] = "Paper Mario"
    assert module_launch.dropped_patch_route("C:/Downloads/MW_P1.unregistered") == ("Paper Mario", "papermario")
    assert drop_core["rescans"] == 0


def test_dropped_patch_rescans_custom_worlds_added_after_boot(module_launch, drop_core):
    drop_core["manifests"]["C:/Downloads/MW_P1.apnew"] = "New Game"
    drop_core["custom"]["New Game"] = "new_game"
    assert module_launch.dropped_patch_route("C:/Downloads/MW_P1.apnew") == ("New Game", "new_game")
    assert drop_core["rescans"] == 1


def test_dropped_patch_for_unknown_game_has_no_module(module_launch, drop_core):
    drop_core["manifests"]["C:/Downloads/MW_P1.apnew"] = "New Game"
    assert module_launch.dropped_patch_route("C:/Downloads/MW_P1.apnew") == ("New Game", None)
