"""World manager build and takeover on the live app (components/legacy_manager.py).

The module is pure Python, so it is loaded by file path with nothing
stubbed; the mwgg_gui package __init__ (and Kivy) never import.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "legacy_manager.py"

_DEFAULT_TITLE = "MultiworldGG"


@pytest.fixture(scope="module")
def legacy_manager():
    spec = importlib.util.spec_from_file_location("legacy_manager_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


class _Frontend:
    """MultiMDApp shape: a StringProperty base_title, kivy-style dispatch, and
    an on_start that does nothing on a phantom."""

    base_title = _DEFAULT_TITLE
    root = None

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.events = []
        self._legacy_kvui_manager = None

    def property(self, name):
        return types.SimpleNamespace(defaultvalue=_DEFAULT_TITLE)

    def dispatch(self, event):
        getattr(self, event)()

    def on_start(self):
        pass

    def _attach_legacy_surface(self, live):
        self.events.append("attach")

    def build(self):
        self.events.append("build")
        return "root layout"


@pytest.fixture
def live():
    return _Frontend()


def test_phantom_without_override_builds_once_and_starts_nothing(legacy_manager, live):
    world = types.new_class("World", (_Frontend,))
    manager = legacy_manager.build_legacy_manager(live, "ctx", world)
    assert isinstance(manager, world)
    assert manager.ctx == "ctx"
    assert manager.events == ["attach", "build"]
    assert manager.root == "root layout"
    assert live._legacy_kvui_manager is manager
    assert live.base_title == _DEFAULT_TITLE


def test_phantom_on_start_override_runs_once_after_registration(legacy_manager, live):
    class World(_Frontend):
        base_title = "World Client"

        def on_start(self):
            self.events.append(("on_start", live._legacy_kvui_manager is self, live.base_title))

    manager = legacy_manager.build_legacy_manager(live, "ctx", World)
    assert manager.events == ["attach", "build", ("on_start", True, "World Client")]


def test_run_gui_phantom_instance_is_built_not_recreated(legacy_manager, live):
    class World(_Frontend):
        made = 0

        def __init__(self, ctx=None):
            super().__init__(ctx)
            type(self).made += 1

        def on_start(self):
            self.events.append("on_start")

    world = World("ctx")
    assert legacy_manager.build_legacy_manager(live, "ctx", world) is world
    assert World.made == 1
    assert world.events == ["attach", "build", "on_start"]
    assert live._legacy_kvui_manager is world


def test_failing_on_start_is_logged_and_the_manager_kept(legacy_manager, live, caplog):
    class World(_Frontend):
        def on_start(self):
            raise AttributeError("log_panels")

    with caplog.at_level(logging.ERROR, logger="Client"):
        manager = legacy_manager.build_legacy_manager(live, "ctx", World)
    assert live._legacy_kvui_manager is manager
    assert "Legacy client on_start failed" in caplog.text


class _GameManager:
    """kvui.GameManager shape: it builds itself against the live app."""

    calls: list

    def __init__(self, ctx):
        self.ctx = ctx

    @classmethod
    def build_for_live_app(cls, ctx, app, **kwargs):
        cls.calls.append((ctx, app, kwargs))
        return kwargs.get("manager") or cls(ctx)


def test_game_manager_class_keeps_the_two_argument_call(legacy_manager, live):
    world = types.new_class("World", (_GameManager,), exec_body=lambda ns: ns.update(calls=[]))
    manager = legacy_manager.build_legacy_manager(live, "ctx", world)
    assert world.calls == [("ctx", live, {})]
    assert isinstance(manager, world)


def test_run_gui_game_manager_instance_is_passed_through(legacy_manager, live):
    world = types.new_class("World", (_GameManager,), exec_body=lambda ns: ns.update(calls=[]))
    made = world("ctx")
    assert legacy_manager.build_legacy_manager(live, "ctx", made) is made
    assert world.calls == [("ctx", live, {"manager": made})]


class _Ctx:
    def __init__(self, can_takeover):
        self.can_takeover = can_takeover
        self.took_over = False
        self.errors = 0

    def _can_takeover_existing_ui(self):
        return self.can_takeover

    async def _takeover_existing_ui(self):
        self.took_over = True

    def _error_callback(self):
        self.errors += 1


def test_take_over_live_app_awaits_the_takeover(legacy_manager):
    ctx = _Ctx(can_takeover=True)
    asyncio.run(legacy_manager.take_over_live_app(ctx))
    assert ctx.took_over
    assert ctx.errors == 0


def test_take_over_without_a_live_app_fires_the_error_callback(legacy_manager, caplog):
    ctx = _Ctx(can_takeover=False)
    with caplog.at_level(logging.CRITICAL, logger="Client"):
        asyncio.run(legacy_manager.take_over_live_app(ctx))
    assert not ctx.took_over
    assert ctx.errors == 1
    assert "Client did not launch properly" in caplog.text
