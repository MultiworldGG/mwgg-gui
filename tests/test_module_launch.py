"""Routed-launch feedback policy (components/module_launch.py).

The module is Kivy-free and loaded by file path; BaseUtils and
subprocess.Popen are stubbed so the launcher spawn is checked without
starting a process.
"""
from __future__ import annotations

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


def test_patch_launch_announces_the_patch_and_the_picker(module_launch):
    lines = module_launch.launch_status_lines(
        "papermario", patch_file="C:/Users/me/Downloads/MW_1_Player.appm64",
        server_address="host:38281")
    assert lines[0] == "Patching MW_1_Player.appm64..."
    assert "file picker" in lines[1]


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
