"""Re-entrant attribute forwarding on the live app (components/live_forwarding.py).

The mixin is pure Python, so it is loaded by file path with nothing
stubbed; the mwgg_gui package __init__ (and Kivy) never import.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "live_forwarding.py"


@pytest.fixture(scope="module")
def live_forwarding():
    spec = importlib.util.spec_from_file_location("live_forwarding_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


class _Manager:
    """kvui.GameManager shape: missing names go to the running app, and
    only a RuntimeError from it becomes AttributeError."""

    def __init__(self, app):
        self._app = app

    def __getattr__(self, name):
        try:
            return getattr(self._app, name)
        except RuntimeError as e:
            raise AttributeError(name) from e


@pytest.fixture
def frontend(live_forwarding):
    """A fresh MultiMDApp-shaped class per test so the singleton slot never leaks."""
    return types.new_class("Frontend", (live_forwarding.LiveForwarding,))


@pytest.fixture
def live(frontend):
    app = frontend()
    frontend._active_instance = app
    return app


def test_missing_name_with_forwarding_manager_returns_default(live):
    live._legacy_kvui_manager = _Manager(live)
    assert getattr(live, "does_not_exist", None) is None
    assert not hasattr(live, "does_not_exist")
    with pytest.raises(AttributeError):
        live.does_not_exist


def test_manager_names_resolve_on_the_live_app(live):
    manager = _Manager(live)
    manager.custom = "world hook"
    live._legacy_kvui_manager = manager
    assert live.custom == "world hook"


def test_phantom_resolves_live_app_names(frontend, live):
    marker = object()
    live.screen_manager = marker
    phantom = frontend()
    assert phantom.screen_manager is marker


def test_phantom_missing_name_with_forwarding_manager_returns_default(frontend, live):
    phantom = frontend()
    live._legacy_kvui_manager = _Manager(phantom)
    assert getattr(phantom, "does_not_exist", None) is None
    assert getattr(live, "does_not_exist", None) is None


def test_phantom_registered_as_manager_returns_default(frontend, live):
    live._legacy_kvui_manager = frontend()
    assert getattr(live, "does_not_exist", None) is None


def test_standalone_instance_raises_for_missing_names(frontend):
    assert getattr(frontend(), "does_not_exist", None) is None


def test_lookup_after_a_miss_still_resolves(live):
    manager = _Manager(live)
    live._legacy_kvui_manager = manager
    assert getattr(live, "custom", None) is None
    manager.custom = "world hook"
    assert live.custom == "world hook"
