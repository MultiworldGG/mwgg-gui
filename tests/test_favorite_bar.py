"""Favorites row geometry and pull-out gesture (launcher/launcher_favorite_bar.py).

The module is loaded by file path with Kivy, KivyMD and mwgg_igdb stubbed;
widget bases are plain classes, so instances are built with object.__new__
and given only the attributes each method reads.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "launcher" / "launcher_favorite_bar.py"


class _Animation:
    started: list = []

    def __init__(self, **props):
        self.props = props
        self.callbacks = []

    def bind(self, on_complete):
        self.callbacks.append(on_complete)

    def start(self, widget):
        _Animation.started.append((widget, self))

    @staticmethod
    def cancel_all(widget, *props):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _base(name):
    return type(name, (), {})


@pytest.fixture(scope="module")
def favorite_bar():
    prop = lambda *args, **kwargs: None  # noqa: E731
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.animation": _stub("kivy.animation", Animation=_Animation),
        "kivy.app": _stub("kivy.app", App=_base("App")),
        "kivy.clock": _stub("kivy.clock", Clock=types.SimpleNamespace()),
        "kivy.lang": _stub("kivy.lang", Builder=types.SimpleNamespace(load_string=prop)),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivy.properties": _stub("kivy.properties", **dict.fromkeys(
            ("ColorProperty", "ListProperty", "ObjectProperty", "StringProperty"), prop)),
        "kivymd": _stub("kivymd"),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.boxlayout": _stub("kivymd.uix.boxlayout", MDBoxLayout=_base("MDBoxLayout")),
        "kivymd.uix.button": _stub("kivymd.uix.button", MDIconButton=_base("MDIconButton")),
        "kivymd.uix.imagelist": _stub("kivymd.uix.imagelist", MDSmartTile=_base("MDSmartTile"),
                                      MDSmartTileImage=_base("MDSmartTileImage")),
        "kivymd.uix.scrollview": _stub("kivymd.uix.scrollview", MDScrollView=_base("MDScrollView")),
        "mwgg_igdb": _stub("mwgg_igdb", GameIndex=None),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("launcher_favorite_bar_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


@pytest.fixture(autouse=True)
def _clear_animations():
    _Animation.started = []


class _Tile:
    def __init__(self, x, module="game"):
        self.x, self.y, self.width, self.height, self.game_module = x, 0, 85, 128, module

    def collide_point(self, x, y):
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


def _row(favorite_bar, tiles=14, parent_width=690, scroll_x=0.0, is_manual=False, velocity=0):
    row = object.__new__(favorite_bar.FavoritesScroll)
    children = [_Tile(i * 95, f"game{i:02d}") for i in range(tiles)]
    row.favorites = types.SimpleNamespace(children=children, spacing=10, width=tiles * 95 - 10)
    row.parent = types.SimpleNamespace(width=parent_width)
    row.effect_x = types.SimpleNamespace(is_manual=is_manual, velocity=velocity, cancelled=False)
    row.effect_x.cancel = lambda: setattr(row.effect_x, "cancelled", True)
    row.scroll_x = scroll_x
    row.scroll_distance = 20
    row.to_local = lambda x, y: (x, y)
    return row


def test_view_is_a_whole_number_of_tiles(favorite_bar):
    row = _row(favorite_bar, parent_width=690)
    row._settle_row()
    assert row.width == 7 * 95 - 10


def test_resting_scroll_glides_to_the_nearest_tile_edge(favorite_bar):
    span = 14 * 95 - 10 - (7 * 95 - 10)
    row = _row(favorite_bar, scroll_x=1.4 * 95 / span)
    row._settle_row()
    [(widget, anim)] = _Animation.started
    assert widget is row
    assert anim.props["scroll_x"] == pytest.approx(95 / span)


@pytest.mark.parametrize("state", [{"is_manual": True}, {"velocity": 120.0}])
def test_no_snap_while_dragging_or_flinging(favorite_bar, state):
    row = _row(favorite_bar, scroll_x=0.3, **state)
    row._settle_row()
    assert _Animation.started == []


def test_a_row_that_fits_never_scrolls(favorite_bar):
    row = _row(favorite_bar, tiles=5, scroll_x=0.3)
    row._settle_row()
    assert _Animation.started == []


def _touch(start, end):
    return types.SimpleNamespace(ox=start[0], oy=start[1], x=end[0], y=end[1])


def test_pull_needs_a_mostly_upward_drag_that_starts_on_a_tile(favorite_bar):
    row = _row(favorite_bar)
    assert not row._start_pull(_touch((100, 60), (100, 75)))
    assert not row._start_pull(_touch((100, 60), (160, 100)))
    assert not row._start_pull(_touch((90, 60), (90, 100)))
    assert not row.effect_x.cancelled
    assert row._start_pull(_touch((100, 60), (110, 100)))
    assert row._pulled.game_module == "game01"
    assert row.effect_x.cancelled


def _tile(favorite_bar):
    tile = object.__new__(favorite_bar.Favorite)
    tile.y, tile.height, tile.opacity, tile._slot_y, tile.game_module = 0, 128, 1, None, "alttp"
    removed = []
    tile.app = types.SimpleNamespace(launcher_screen=types.SimpleNamespace(remove_from_favorite_bar=removed.append))
    return tile, removed


def test_tile_pulled_past_a_third_leaves_the_bar(favorite_bar):
    tile, removed = _tile(favorite_bar)
    tile.pull(64)
    assert (tile.y, tile.opacity) == (64, 0.5)
    tile.release(64)
    [(_, anim)] = _Animation.started
    assert anim.props["opacity"] == 0
    for callback in anim.callbacks:
        callback(anim, tile)
    assert removed == ["alttp"]


def test_short_pull_drops_back_into_its_slot(favorite_bar):
    tile, removed = _tile(favorite_bar)
    tile.pull(30)
    tile.release(30)
    [(_, anim)] = _Animation.started
    assert anim.props == {"y": 0, "opacity": 1, "d": .15, "t": "out_quad"}
    assert anim.callbacks == []
    assert removed == []
