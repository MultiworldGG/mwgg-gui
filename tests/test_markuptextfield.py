"""Empty-text refresh in the console text field (overrides/markuptextfield.py).

markuptextfield.py imports Kivy and KivyMD at module level, so it is loaded by
file path with those imports stubbed; properties collapse to their defaults and
TextInput is a recorder standing in for Kivy's _refresh_text.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "overrides" / "markuptextfield.py"


class _Stub:
    def __init__(self, *args, **kwargs):
        pass


class _TextInput:
    _lines: list[str] = []

    def _refresh_text(self, text, *largs):
        self.refreshed = (text, largs)


def _base(name):
    return type(name, (), {})


def _prop(default=None, *args, **kwargs):
    return default


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def markuptextfield():
    noop = lambda *args, **kwargs: None  # noqa: E731
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.core": _stub("kivy.core"),
        "kivy.core.window": _stub("kivy.core.window", Window=types.SimpleNamespace()),
        "kivy.core.clipboard": _stub("kivy.core.clipboard", Clipboard=None),
        "kivy.core.text": _stub("kivy.core.text"),
        "kivy.core.text.markup": _stub("kivy.core.text.markup", MarkupLabel=_Stub),
        "kivy.lang": _stub("kivy.lang", Builder=types.SimpleNamespace(load_string=noop)),
        "kivy.properties": _stub("kivy.properties", **dict.fromkeys(
            ("ObjectProperty", "NumericProperty", "VariableListProperty", "ColorProperty", "BooleanProperty",
             "StringProperty", "OptionProperty", "ListProperty"), _prop)),
        "kivy.base": _stub("kivy.base", EventLoop=None),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivy.clock": _stub("kivy.clock", Clock=types.SimpleNamespace()),
        "kivy.animation": _stub("kivy.animation", Animation=_Stub),
        "kivy.config": _stub("kivy.config", Config=None),
        "kivy.effects": _stub("kivy.effects"),
        "kivy.effects.scroll": _stub("kivy.effects.scroll", ScrollEffect=_Stub),
        "kivy.uix": _stub("kivy.uix"),
        "kivy.uix.textinput": _stub("kivy.uix.textinput", TextInput=_TextInput),
        "kivy.cache": _stub("kivy.cache", Cache=types.SimpleNamespace(
            register=noop, append=noop, get=noop, remove=noop)),
        "kivymd": _stub("kivymd"),
        "kivymd.theming": _stub("kivymd.theming", ThemableBehavior=_base("ThemableBehavior")),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.menu": _stub("kivymd.uix.menu", MDDropdownMenu=_base("MDDropdownMenu")),
        "kivymd.uix.tooltip": _stub("kivymd.uix.tooltip", MDTooltipPlain=_base("MDTooltipPlain")),
        "kivymd.uix.behaviors": _stub("kivymd.uix.behaviors", HoverBehavior=_base("HoverBehavior")),
        "kivymd.uix.textfield": _stub("kivymd.uix.textfield", **dict.fromkeys(
            ("MDTextFieldHelperText", "MDTextFieldTrailingIcon", "MDTextFieldHintText", "MDTextFieldLeadingIcon"),
            _Stub)),
        "kivymd.uix.button": _stub("kivymd.uix.button", MDFabButton=_Stub),
        "mwgg_gui": _stub("mwgg_gui"),
        "mwgg_gui.overrides": _stub("mwgg_gui.overrides"),
        "mwgg_gui.overrides.hoverlabel": _stub("mwgg_gui.overrides.hoverlabel", ref_span_color=noop),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("mwgg_gui.overrides.markuptextfield_under_test", _PATH)
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
def field(markuptextfield):
    return object.__new__(markuptextfield.MarkupTextField)


def test_empty_text_tokenizes_to_one_empty_token(field):
    # Kivy's _split_smart builds no lines from no tokens, and _refresh_text then indexes _lines_labels[0].
    assert list(field._tokenize("")) == [""]


def test_empty_text_reaches_kivy_refresh(field):
    # Skipping it leaves _lines empty, and TextInput.get_cursor_from_xy raises IndexError on the next click.
    field._refresh_text("")
    assert field.refreshed == ("", ())
