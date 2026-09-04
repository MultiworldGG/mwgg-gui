"""Compact-mode preference and window geometry (components/layout_mode.py).

layout_mode.py imports kivy.core.window at module level, so it is loaded by
file path with the Kivy imports stubbed for the duration of the load; the
helpers under test are pure Python.
"""
from __future__ import annotations

import configparser
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "layout_mode.py"


class _Property:
    def __init__(self, *args, **kwargs):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def layout_mode():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.core": _stub("kivy.core"),
        "kivy.clock": _stub("kivy.clock", Clock=types.SimpleNamespace()),
        "kivy.core.window": _stub("kivy.core.window", Window=types.SimpleNamespace()),
        "kivy.event": _stub("kivy.event", EventDispatcher=type("EventDispatcher", (), {})),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivy.properties": _stub(
            "kivy.properties",
            AliasProperty=_Property,
            BooleanProperty=_Property,
            NumericProperty=_Property,
        ),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("layout_mode_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


def _config(**client) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.add_section("client")
    for key, value in client.items():
        config.set("client", key, value)
    return config


def test_compact_mode_key_wins(layout_mode):
    assert layout_mode.read_compact_mode(_config(compact_mode="1")) is True
    assert layout_mode.read_compact_mode(_config(compact_mode="0")) is False
    # The explicit key outranks the legacy orientation value.
    assert layout_mode.read_compact_mode(
        _config(compact_mode="0", device_orientation="Portrait")) is False


def test_legacy_portrait_orientation_means_compact(layout_mode):
    assert layout_mode.read_compact_mode(_config(device_orientation="Portrait")) is True
    assert layout_mode.read_compact_mode(_config(device_orientation="Landscape")) is False
    assert layout_mode.read_compact_mode(_config()) is False


def test_window_geometry_per_mode(layout_mode):
    desktop_size, desktop_min = layout_mode.window_geometry(False)
    compact_size, compact_min = layout_mode.window_geometry(True)
    assert desktop_size == (1100, 700) and desktop_min == (600, 700)
    assert compact_size[0] < compact_size[1], "compact is a portrait window"
    assert compact_min[0] <= compact_size[0] and compact_min[1] <= compact_size[1]
    assert compact_min[0] < desktop_min[0]
