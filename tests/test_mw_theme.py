"""Test for mwgg_gui/components/mw_theme.py markup color loading.

mw_theme.py imports kivy/kivymd at module level (including
kivy.core.window, which opens a real window), so it is loaded by file
path with those imports stubbed in sys.modules for the duration of the
load. The color-loading logic under test is pure Python.
"""
from __future__ import annotations

import configparser
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MW_THEME_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "mw_theme.py"
)


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class _Property:
    def __init__(self, *args, **kwargs):
        pass


def _load_mw_theme():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.core": _stub("kivy.core"),
        "kivy.core.text": _stub("kivy.core.text", LabelBase=type("LabelBase", (), {})),
        "kivy.core.window": _stub(
            "kivy.core.window",
            Window=types.SimpleNamespace(height=800, bind=lambda **kwargs: None),
        ),
        "kivy.metrics": _stub(
            "kivy.metrics",
            sp=lambda value: value,
            dp=lambda value: value,
            Metrics=types.SimpleNamespace(fontscale=1.0),
        ),
        "kivy.properties": _stub(
            "kivy.properties",
            StringProperty=_Property,
            BooleanProperty=_Property,
            BoundedNumericProperty=_Property,
        ),
        "kivy.lang": _stub(
            "kivy.lang",
            Builder=types.SimpleNamespace(load_string=lambda *args, **kwargs: None),
        ),
        "kivy.utils": _stub("kivy.utils", hex_colormap={}),
        "kivymd": _stub("kivymd"),
        "kivymd.app": _stub("kivymd.app", MDApp=type("MDApp", (), {})),
        "kivymd.theming": _stub(
            "kivymd.theming", ThemableBehavior=type("ThemableBehavior", (), {})
        ),
        "PIL": _stub("PIL", Image=types.SimpleNamespace()),
        "numpy": _stub("numpy"),
        "NetUtils": _stub("NetUtils", TEXT_COLORS={}),
        "BaseUtils": _stub("BaseUtils", local_path=lambda *parts: ""),
        "mwgg_gui": _stub("mwgg_gui"),
        "mwgg_gui.overrides": _stub("mwgg_gui.overrides", md_icons={}),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "mw_theme_under_test", _MW_THEME_PATH
        )
        module = importlib.util.module_from_spec(spec)
        # dataclass resolves string annotations via sys.modules[__module__].
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


mw_theme = _load_mw_theme()


def test_load_markup_color_forwards_theme_style_index():
    config = configparser.ConfigParser()
    config.add_section("markup_tags")
    config.set("markup_tags", "player1_color", "111111,eeeeee")

    theme = object.__new__(mw_theme.DefaultTheme)
    theme.app_config = config
    theme.markup_tags_theme = mw_theme.MarkupTagsTheme()

    assert theme.load_markup_color("player1_color", 1) == ["111111", "eeeeee"]
    assert mw_theme.TEXT_COLORS["player1_color"] == "eeeeee"
    theme.load_markup_color("player1_color", 0)
    assert mw_theme.TEXT_COLORS["player1_color"] == "111111"

    # Color absent from config: falls back to the packaged defaults.
    default = mw_theme.DEFAULT_TEXT_COLORS["trap_item_color"]
    assert theme.load_markup_color("trap_item_color", 1) == default
    assert mw_theme.TEXT_COLORS["trap_item_color"] == default[1]


class _MemoryConfig(configparser.ConfigParser):
    """ConfigParser stand-in for kivy's, whose write() takes no file."""
    def __init__(self):
        super().__init__()
        self.writes = 0

    def write(self):
        self.writes += 1


def _theme(config, game_module="", style="Dark"):
    theme = object.__new__(mw_theme.DefaultTheme)
    theme.app_config = config
    theme.game_module = game_module
    theme._theme_style = style
    return theme


@pytest.fixture
def palettes(monkeypatch):
    monkeypatch.setattr(mw_theme, "hex_colormap", {"purple": "", "green": "", "blue": ""})


def test_load_primary_palette_prefers_game_override(palettes):
    config = _MemoryConfig()
    config.add_section("client")
    config.set("client", "primary_palette", "Blue")
    config.add_section("game_settings")
    config.set("game_settings", "albw_primary_palette", "green")

    assert _theme(config).load_primary_palette() == "Blue"
    assert _theme(config, "albw").load_primary_palette() == "Green"
    assert _theme(config, "kh2").load_primary_palette() == "Blue"


def test_load_primary_palette_rejects_unknown_names(palettes):
    config = _MemoryConfig()
    config.add_section("client")
    config.set("client", "primary_palette", "Blue")
    config.add_section("game_settings")
    config.set("game_settings", "albw_primary_palette", "Mauve")
    default = mw_theme.THEME_OPTIONS["Dark"][0][0]

    assert _theme(config, "albw").load_primary_palette() == default
    assert _theme(_MemoryConfig(), "albw").load_primary_palette() == default


def test_save_primary_palette_routes_by_scope():
    config = _MemoryConfig()
    config.add_section("client")
    theme = _theme(config, "albw")

    theme.save_primary_palette("Green", for_game=True)
    assert config.get("game_settings", "albw_primary_palette") == "Green"
    assert not config.has_option("client", "primary_palette")
    assert theme.primary_palette == "Green"

    theme.save_primary_palette("Blue")
    assert config.get("client", "primary_palette") == "Blue"
    assert config.get("game_settings", "albw_primary_palette") == "Green"

    # Launcher (no game) ignores for_game and writes the root setting.
    launcher = _theme(config)
    launcher.save_primary_palette("Purple", for_game=True)
    assert config.get("client", "primary_palette") == "Purple"
    assert config.writes == 3


def test_set_game_palette_enabled_pins_and_drops_override():
    config = _MemoryConfig()
    config.add_section("client")
    theme = _theme(config, "albw")
    theme._primary_palette = "Green"

    theme.set_game_palette_enabled(True)
    assert config.get("game_settings", "albw_primary_palette") == "Green"

    theme.set_game_palette_enabled(False)
    assert not config.has_option("game_settings", "albw_primary_palette")
    assert config.writes == 2

    # No section yet and no game: both are no-ops.
    _theme(_MemoryConfig(), "albw").set_game_palette_enabled(False)
    _theme(config).set_game_palette_enabled(True)
    assert config.writes == 2
