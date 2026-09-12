"""First-launch tour model (components/onboarding.py): the step lists, the
client.ini flags, and the spotlight/card placement math."""
from __future__ import annotations

import configparser
import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "onboarding.py"


@pytest.fixture(scope="module")
def onboarding():
    spec = importlib.util.spec_from_file_location("onboarding_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves postponed annotations through sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    yield module
    sys.modules.pop(spec.name, None)


def _config(**client) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if client:
        config.add_section("client")
    for key, value in client.items():
        config.set("client", key, value)
    return config


def test_tours_cover_both_roles_with_unique_targets(onboarding):
    assert set(onboarding.TOURS) == {"launcher", "client"}
    for role, steps in onboarding.TOURS.items():
        assert steps[0].target == "", f"{role} opens with a centered welcome card"
        targets = [step.target for step in steps if step.target]
        assert len(targets) == len(set(targets)), f"{role} spotlights repeat"
        assert all(step.title and step.body for step in steps)
        assert steps[-1].target == "menu", f"{role} ends on the hamburger menu"


def test_launcher_tour_walks_the_standard_flow(onboarding):
    targets = [step.target for step in onboarding.LAUNCHER_TOUR if step.target]
    order = [targets.index(key) for key in
             ("search", "game_list", "client_type", "connection", "launch", "menu")]
    assert order == sorted(order)
    assert "favorites" in targets


def test_client_tour_shows_input_hint_and_extra_tabs(onboarding):
    targets = [step.target for step in onboarding.CLIENT_TOUR if step.target]
    assert targets[:3] == ["input", "hint", "nav"]


def test_compact_text_falls_back_to_body(onboarding):
    step = onboarding.TourStep("x", "T", "desktop", "compact")
    assert step.text(compact=False) == "desktop"
    assert step.text(compact=True) == "compact"
    assert onboarding.TourStep("x", "T", "desktop").text(compact=True) == "desktop"


def test_tour_pending_until_marked_done(onboarding):
    config = _config()
    assert onboarding.tour_pending(config, "launcher"), "absent key means not shown yet"
    assert onboarding.tour_pending(_config(onboarding_launcher="0"), "launcher")
    assert not onboarding.tour_pending(_config(onboarding_launcher="1"), "launcher")
    onboarding.mark_tour_done(config, "launcher")
    assert config.get("client", "onboarding_launcher") == "1"
    assert not onboarding.tour_pending(config, "launcher")
    assert onboarding.tour_pending(config, "client"), "roles are tracked separately"


def test_union_rect(onboarding):
    assert onboarding.union_rect([]) is None
    assert onboarding.union_rect([(10, 10, 20, 20)]) == (10, 10, 20, 20)
    assert onboarding.union_rect(
        [(10, 10, 20, 20), (0, 25, 5, 5), (35, 0, 5, 5)]) == (0, 0, 40, 30)


def test_spotlight_rect_pads_and_clips(onboarding):
    bounds = (0, 0, 100, 100)
    assert onboarding.spotlight_rect((10, 10, 20, 20), 5, bounds) == (5, 5, 30, 30)
    assert onboarding.spotlight_rect((0, 0, 20, 20), 5, bounds) == (0, 0, 25, 25)
    assert onboarding.spotlight_rect((90, 90, 20, 20), 5, bounds) == (85, 85, 15, 15)


def test_place_card_centers_without_target(onboarding):
    assert onboarding.place_card((100, 50), (0, 0, 400, 300)) == (150, 125)


def test_place_card_prefers_below_then_above_then_sides(onboarding):
    bounds = (0, 0, 400, 300)
    card = (100, 50)
    # Room below: the card hangs under the target, centered on it.
    assert onboarding.place_card(card, bounds, (150, 200, 40, 20), margin=10) == (120, 140)
    # Target on the floor: the card goes above.
    assert onboarding.place_card(card, bounds, (150, 0, 40, 20), margin=10) == (120, 30)
    # Full-height column on the left: the card sits to its right.
    x, y = onboarding.place_card(card, bounds, (0, 0, 60, 300), margin=10)
    assert x == 70 and 10 <= y <= 240
    # Full-height column on the right: the card sits to its left.
    x, y = onboarding.place_card(card, bounds, (340, 0, 60, 300), margin=10)
    assert x == 230 and 10 <= y <= 240


def test_place_card_stays_inside_bounds(onboarding):
    bounds = (0, 0, 400, 300)
    x, y = onboarding.place_card((100, 50), bounds, (0, 200, 10, 10), margin=10)
    assert x == 10 and y == 140, "left edge target: card clamps to the margin"
    x, y = onboarding.place_card((100, 50), bounds, (395, 200, 10, 10), margin=10)
    assert x == 290, "right edge target: card clamps to the margin"


def test_place_card_falls_back_to_center_when_nothing_fits(onboarding):
    assert onboarding.place_card((100, 50), (0, 0, 120, 60), (0, 0, 120, 60)) == (10, 5)
