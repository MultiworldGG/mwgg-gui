"""Class-level base_title writes from per-world client code (components/titlebar.py).

titlebar.py imports Kivy and KivyMD at module level, so it is loaded by
file path with those imports stubbed for the duration of the load; the
metaclass under test is pure Python.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "titlebar.py"


class _Stub:
    def __init__(self, *args, **kwargs):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def titlebar():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.core": _stub("kivy.core"),
        "kivy.core.window": _stub("kivy.core.window", Window=types.SimpleNamespace()),
        "kivy.lang": _stub("kivy.lang", Builder=types.SimpleNamespace(load_string=lambda kv: None)),
        "kivy.properties": _stub("kivy.properties", ObjectProperty=_Stub),
        "kivy.uix": _stub("kivy.uix"),
        "kivy.uix.effectwidget": _stub(
            "kivy.uix.effectwidget", HorizontalBlurEffect=_Stub, VerticalBlurEffect=_Stub),
        "kivymd": _stub("kivymd"),
        "kivymd.app": _stub("kivymd.app", MDApp=_Stub),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.boxlayout": _stub("kivymd.uix.boxlayout", MDBoxLayout=_Stub),
        "kivymd.uix.button": _stub("kivymd.uix.button", MDIconButton=_Stub),
        "mwgg_gui": _stub("mwgg_gui"),
        "mwgg_gui.components": _stub("mwgg_gui.components"),
        "mwgg_gui.components.safe_effect_widget": _stub(
            "mwgg_gui.components.safe_effect_widget", SafeEffectWidget=_Stub),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("titlebar_under_test", _PATH)
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


@pytest.fixture
def frontend(titlebar):
    """A frontend class shaped like MultiMDApp: a property-like object on
    the class and the singleton slot the metaclass consults."""
    marker = object()
    cls = titlebar.LiveTitleMeta(
        "Frontend", (), {"_active_instance": None, "base_title": marker})
    return cls, marker


def test_class_write_lands_on_live_instance_and_keeps_the_property(frontend):
    cls, marker = frontend
    live = types.SimpleNamespace(base_title="MultiworldGG")
    cls._active_instance = live
    cls.base_title = "MultiworldGG BizHawk Client"
    assert live.base_title == "MultiworldGG BizHawk Client"
    assert vars(cls)["base_title"] is marker


def test_subclass_write_reaches_the_live_instance(frontend):
    cls, marker = frontend
    live = types.SimpleNamespace(base_title="MultiworldGG")
    cls._active_instance = live
    sub = types.new_class("Sub", (cls,))
    sub.base_title = "Sub Client"
    assert live.base_title == "Sub Client"
    assert "base_title" not in vars(sub)


def test_class_write_without_live_instance_falls_through(frontend):
    cls, _ = frontend
    cls.base_title = "Standalone"
    assert vars(cls)["base_title"] == "Standalone"


def test_non_string_class_writes_pass_through(frontend):
    cls, _ = frontend
    live = types.SimpleNamespace(base_title="MultiworldGG")
    cls._active_instance = live
    replacement = object()
    cls.base_title = replacement
    assert vars(cls)["base_title"] is replacement
    assert live.base_title == "MultiworldGG"


def test_other_attributes_are_untouched(frontend):
    cls, _ = frontend
    live = types.SimpleNamespace(base_title="MultiworldGG")
    cls._active_instance = live
    cls.logging_pairs = [("Foo", "Bar")]
    assert vars(cls)["logging_pairs"] == [("Foo", "Bar")]
    assert not hasattr(live, "logging_pairs")
