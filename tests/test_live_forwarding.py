"""Re-entrant attribute forwarding on the live app, and kvui hooks that prefer
a legacy manager's override (components/live_forwarding.py).

The module is pure Python, so it is loaded by file path with nothing
stubbed; the mwgg_gui package __init__ (and Kivy) never import.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "live_forwarding.py"
_POOL = 36_000_000


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


class _Label:
    def __init__(self, text):
        self.text = text


class _Layout(list):
    add_widget = list.append


def _bars(ctx):
    return f"EL: {ctx.current_energy_link_value / 24_000_000:g} bars"


@pytest.fixture
def frontend(live_forwarding):
    """A fresh MultiMDApp-shaped class per test so the singleton slot never
    leaks; the energy-link hooks mirror MultiMDApp's."""
    prefer = live_forwarding.prefer_manager_override

    class Frontend(live_forwarding.LiveForwarding):
        def __init__(self, ctx=None):
            self.ctx = ctx
            self._connect_layout = _Layout()

        def _resolve_live_app(self):
            live = type(self)._active_instance
            return self if live is None else live

        @property
        def connect_layout(self):
            return self._resolve_live_app()._connect_layout

        @prefer("energy_link_label")
        def enable_energy_link(self):
            live = self._resolve_live_app()
            if "energy_link_label" not in vars(live):
                live.energy_link_label = _Label("Energy Link: Standby")
                live.connect_layout.add_widget(live.energy_link_label)

        @prefer()
        def set_new_energy_link_value(self):
            live = self._resolve_live_app()
            if "energy_link_label" in vars(live):
                live.energy_link_label.text = f"EL: {live.ctx.current_energy_link_value}J"

    return Frontend


@pytest.fixture
def live(frontend):
    app = frontend(types.SimpleNamespace(current_energy_link_value=_POOL))
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


_PLAIN_MANAGERS = {
    "none": lambda frontend, live: None,
    "make_gui": lambda frontend, live: types.new_class("World", (frontend,))(live.ctx),
    "kvui": lambda frontend, live: _Manager(live),
}


@pytest.mark.parametrize("shape", _PLAIN_MANAGERS)
def test_no_override_keeps_default_joule_label(frontend, live, shape):
    live._legacy_kvui_manager = _PLAIN_MANAGERS[shape](frontend, live)
    live.enable_energy_link()
    live.set_new_energy_link_value()
    assert live.connect_layout == [vars(live)["energy_link_label"]]
    assert live.energy_link_label.text == f"EL: {_POOL}J"


def test_make_gui_subclass_value_override_runs_on_live_label(frontend, live):
    class World(frontend):
        def set_new_energy_link_value(self):
            if hasattr(self, "energy_link_label"):
                self.energy_link_label.text = _bars(self.ctx)

    live._legacy_kvui_manager = World(live.ctx)
    live.enable_energy_link()
    live.set_new_energy_link_value()
    assert live.connect_layout == [vars(live)["energy_link_label"]]
    assert live.energy_link_label.text == "EL: 1.5 bars"


def test_make_gui_subclass_super_call_runs_default_once(frontend, live):
    class World(frontend):
        def enable_energy_link(self):
            super().enable_energy_link()
            self.energy_link_label.text = "Drops: Standby"

    live._legacy_kvui_manager = World(live.ctx)
    live.enable_energy_link()
    assert live.connect_layout == [vars(live)["energy_link_label"]]
    assert live.energy_link_label.text == "Drops: Standby"


class _KvuiWorld(_Manager):
    """Upstream kvui.GameManager.enable_energy_link: the label lands on the manager."""

    def enable_energy_link(self):
        if not hasattr(self, "energy_link_label"):
            self.energy_link_label = _Label("Energy Link: Standby")
            self.connect_layout.add_widget(self.energy_link_label)


class _KvuiBarsWorld(_KvuiWorld):
    def set_new_energy_link_value(self):
        if hasattr(self, "energy_link_label"):
            self.energy_link_label.text = _bars(self.ctx)


def test_kvui_enable_override_label_is_adopted_by_live_app(live):
    manager = _KvuiWorld(live)
    live._legacy_kvui_manager = manager
    live.enable_energy_link()
    live.set_new_energy_link_value()
    assert vars(live)["energy_link_label"] is vars(manager)["energy_link_label"]
    assert live.connect_layout == [manager.energy_link_label]
    assert manager.energy_link_label.text == f"EL: {_POOL}J"


def test_kvui_value_override_runs_on_live_app(live):
    manager = _KvuiBarsWorld(live)
    live._legacy_kvui_manager = manager
    live.enable_energy_link()
    live.set_new_energy_link_value()
    assert live.connect_layout == [manager.energy_link_label]
    assert live.energy_link_label.text == "EL: 1.5 bars"


def test_kvui_stub_forwarding_to_running_app_runs_default(live):
    class Stub(_Manager):
        def set_new_energy_link_value(self):
            self._app.set_new_energy_link_value()

    live._legacy_kvui_manager = Stub(live)
    live.enable_energy_link()
    live.set_new_energy_link_value()
    assert live.energy_link_label.text == f"EL: {_POOL}J"
