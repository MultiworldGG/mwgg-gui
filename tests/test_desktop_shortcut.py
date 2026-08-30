"""Tests for mwgg_gui/launcher/desktop_shortcut.py.

The module is Kivy-free but lives under the package, so it is loaded by file
path here (mwgg_gui/__init__ imports the full GUI). Its core-only imports
(BaseUtils, pyshortcuts) are function-local; BaseUtils is stubbed in
sys.modules so the command-building tests run without the beta core.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "mwgg_gui" / "launcher" / "desktop_shortcut.py"
)


@pytest.fixture(scope="module")
def desktop_shortcut():
    spec = importlib.util.spec_from_file_location(
        "desktop_shortcut_under_test", _MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def stub_base_utils(monkeypatch):
    base_utils = types.ModuleType("BaseUtils")
    base_utils.get_client_exe = lambda: ["C:/apps/MultiworldGG.exe"]
    monkeypatch.setitem(sys.modules, "BaseUtils", base_utils)
    monkeypatch.delenv("APPIMAGE", raising=False)
    return base_utils


def test_game_client_command(desktop_shortcut, stub_base_utils):
    assert desktop_shortcut.client_shortcut_command("khddd", "text") == [
        "C:/apps/MultiworldGG.exe", "--game", "khddd", "--client-type", "text",
    ]


def test_tracker_rides_on_the_game_module(desktop_shortcut, stub_base_utils):
    assert desktop_shortcut.client_shortcut_command("khddd", "universal_tracker") == [
        "C:/apps/MultiworldGG.exe", "--game", "khddd",
        "--client-type", "universal_tracker",
    ]


def test_no_game_omits_the_game_flag(desktop_shortcut, stub_base_utils):
    assert desktop_shortcut.client_shortcut_command(None, "text") == [
        "C:/apps/MultiworldGG.exe", "--client-type", "text",
    ]


def test_source_mode_keeps_the_interpreter(desktop_shortcut, stub_base_utils):
    stub_base_utils.get_client_exe = lambda: ["/venv/python", "/src/MultiWorld.py"]
    assert desktop_shortcut.client_shortcut_command(None, "manual") == [
        "/venv/python", "/src/MultiWorld.py", "--client-type", "manual",
    ]


def test_appimage_targets_the_appimage_itself(desktop_shortcut, stub_base_utils,
                                              monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/opt/MultiworldGG.AppImage")
    monkeypatch.setenv("ARGV0", "/home/didi/MultiworldGG.AppImage")
    assert desktop_shortcut.client_shortcut_command("khddd", "text") == [
        "/home/didi/MultiworldGG.AppImage", "--game", "khddd",
        "--client-type", "text",
    ]
