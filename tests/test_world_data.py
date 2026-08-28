"""Unit tests for mwgg_gui/yaml_creator/world_data.py (loaded by file path —
see conftest.py).

Covers the LauncherComponents exe delegation (no hardcoded exe literal can
survive these), the spawn env/cwd/creationflags contract, the retry-once
loop on Generate's reload exit code, and every WorldDataError path.
"""
from __future__ import annotations

import os
import sys
import types
from types import SimpleNamespace

import pytest


def _completed(returncode=0, stdout='{"ok": true}', stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _stub_launcher_components(monkeypatch, exe, component="generate-component"):
    """Mount a fake top-level LauncherComponents module that records the
    delegation calls — the real core module is never imported."""
    calls = {}
    lc = types.ModuleType("LauncherComponents")

    def find_component(name):
        calls["find_component"] = name
        return component

    def get_exe(comp):
        calls["get_exe"] = comp
        return exe

    lc.find_component = find_component
    lc.get_exe = get_exe
    monkeypatch.setitem(sys.modules, "LauncherComponents", lc)
    return calls


# ----- _generate_command: exe resolution delegates -------------------------


def test_generate_command_delegates_to_launcher_components(world_data, monkeypatch):
    sentinel = [sys.executable, os.path.join("sentinel", "Generate.py")]
    calls = _stub_launcher_components(monkeypatch, exe=list(sentinel))
    assert world_data._generate_command() == sentinel
    assert calls == {
        "find_component": "Generate",
        "get_exe": "generate-component",
    }


def test_generate_command_error_when_component_missing(world_data, monkeypatch):
    _stub_launcher_components(monkeypatch, exe=None, component=None)
    with pytest.raises(world_data.WorldDataError):
        world_data._generate_command()


def test_generate_command_error_when_exe_unresolvable(world_data, monkeypatch):
    _stub_launcher_components(monkeypatch, exe=None)
    with pytest.raises(world_data.WorldDataError):
        world_data._generate_command()


# ----- _run_generate: spawn contract ---------------------------------------


@pytest.fixture
def spawn_capture(world_data, monkeypatch):
    """Route _generate_command to a sentinel prefix and capture the single
    subprocess.run invocation."""
    captured = {}
    prefix = [sys.executable, os.path.join("install", "dir", "Generate.py")]
    monkeypatch.setattr(world_data, "_generate_command", lambda: list(prefix))

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _completed()

    monkeypatch.setattr(world_data.subprocess, "run", fake_run)
    monkeypatch.delenv("KIVY_NO_ARGS", raising=False)
    monkeypatch.delenv("SKIP_REQUIREMENTS_UPDATE", raising=False)
    captured["prefix"] = prefix
    return captured


def test_run_generate_argv_env_cwd_creationflags(world_data, spawn_capture, monkeypatch):
    monkeypatch.setattr(world_data, "is_frozen", lambda: False)
    monkeypatch.setattr(world_data, "is_windows", True)
    monkeypatch.setattr(
        world_data.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )

    world_data._run_generate("Some Game", "simple", module="some_module")

    prefix = spawn_capture["prefix"]
    assert spawn_capture["cmd"] == prefix + [
        "--yaml-options",
        "--game", "Some Game",
        "--visibility", "simple",
        "--module", "some_module",
    ]
    kwargs = spawn_capture["kwargs"]
    assert kwargs["cwd"] == os.path.dirname(prefix[-1])
    assert kwargs["timeout"] == world_data._TIMEOUT_SECONDS
    # SKIP_REQUIREMENTS_UPDATE always: blocks ModuleUpdate's frozen
    # self-respawn (Utils.exit_restart_for_update) in the child.
    assert kwargs["env"]["SKIP_REQUIREMENTS_UPDATE"] == "1"
    # KIVY_NO_ARGS only from source.
    assert kwargs["env"]["KIVY_NO_ARGS"] == "1"
    assert kwargs["creationflags"] == 0x08000000


def test_run_generate_frozen_env_omits_kivy_no_args(world_data, spawn_capture, monkeypatch):
    monkeypatch.setattr(world_data, "is_frozen", lambda: True)
    monkeypatch.setattr(world_data, "is_windows", False)

    world_data._run_generate("Some Game", "complex")

    kwargs = spawn_capture["kwargs"]
    assert kwargs["env"]["SKIP_REQUIREMENTS_UPDATE"] == "1"
    assert "KIVY_NO_ARGS" not in kwargs["env"]
    assert "creationflags" not in kwargs
    assert "--module" not in spawn_capture["cmd"]


# ----- load_world_data: retry-once on the reload exit code -----------------


def _patch_run_sequence(world_data, monkeypatch, results):
    prefix = [sys.executable, os.path.join("install", "dir", "Generate.py")]
    monkeypatch.setattr(world_data, "_generate_command", lambda: list(prefix))
    monkeypatch.setattr(world_data, "is_frozen", lambda: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = results[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(world_data.subprocess, "run", fake_run)
    return calls


def test_load_world_data_retries_once_on_reload_exit(world_data, monkeypatch):
    calls = _patch_run_sequence(world_data, monkeypatch, [
        _completed(returncode=world_data._EXIT_NEEDS_RELOAD, stdout="", stderr="installed"),
        _completed(stdout='{"ok": true, "game_name": "G"}'),
    ])
    payload = world_data.load_world_data("G")
    assert payload["ok"] is True
    assert len(calls) == 2


def test_load_world_data_never_retries_twice(world_data, monkeypatch):
    calls = _patch_run_sequence(world_data, monkeypatch, [
        _completed(returncode=world_data._EXIT_NEEDS_RELOAD, stdout="", stderr="x"),
        _completed(returncode=world_data._EXIT_NEEDS_RELOAD, stdout="", stderr="x"),
    ])
    with pytest.raises(world_data.WorldDataError):
        world_data.load_world_data("G")
    assert len(calls) == 2


def test_load_world_data_no_retry_on_success(world_data, monkeypatch):
    calls = _patch_run_sequence(world_data, monkeypatch, [_completed()])
    assert world_data.load_world_data("G")["ok"] is True
    assert len(calls) == 1


def test_exit_needs_reload_constant_pinned(world_data):
    # Must match Generate.EXIT_NEEDS_RELOAD; the beta-side contract test
    # (test/programs/test_yaml_options.py) pins the same value from the
    # other direction.
    assert world_data._EXIT_NEEDS_RELOAD == 10


# ----- load_world_data: WorldDataError paths -------------------------------


def test_error_on_nonzero_exit(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [
        _completed(returncode=1, stdout="", stderr="boom"),
    ])
    with pytest.raises(world_data.WorldDataError, match="code 1"):
        world_data.load_world_data("G")


def test_error_on_timeout(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [
        world_data.subprocess.TimeoutExpired("cmd", world_data._TIMEOUT_SECONDS),
    ])
    with pytest.raises(world_data.WorldDataError, match="Timed out"):
        world_data.load_world_data("G")


def test_error_on_spawn_failure(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [OSError("no such exe")])
    with pytest.raises(world_data.WorldDataError, match="Could not run Generate"):
        world_data.load_world_data("G")


def test_error_on_empty_stdout(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [_completed(stdout="  \n")])
    with pytest.raises(world_data.WorldDataError, match="no output"):
        world_data.load_world_data("G")


def test_error_on_unparseable_stdout(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [
        _completed(stdout="definitely { not json", stderr="diag"),
    ])
    with pytest.raises(world_data.WorldDataError, match="Could not parse") as exc_info:
        world_data.load_world_data("G")
    assert "diag" in (exc_info.value.trace or "")


def test_error_on_ok_false_payload(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [
        _completed(stdout='{"ok": false, "error": "nope", "trace": "tb"}'),
    ])
    with pytest.raises(world_data.WorldDataError, match="nope") as exc_info:
        world_data.load_world_data("G")
    assert exc_info.value.trace == "tb"


def test_recovers_last_json_line_from_noisy_stdout(world_data, monkeypatch):
    _patch_run_sequence(world_data, monkeypatch, [
        _completed(stdout='stray warning line\n{"ok": true, "game_name": "G"}'),
    ])
    assert world_data.load_world_data("G")["ok"] is True
