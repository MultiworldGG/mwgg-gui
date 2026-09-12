"""
First-launch tour model: the coach-mark steps each role plays, the client.ini
flags that record a finished tour, and the spotlight/card placement math.

Kivy-free on purpose: the GUI-side unit tests load it by file path. The
overlay that plays the steps is components/tour_overlay.py.
"""
from __future__ import annotations

__all__ = ("TourStep", "LAUNCHER_TOUR", "CLIENT_TOUR", "TOURS", "config_key",
           "tour_pending", "mark_tour_done", "union_rect", "spotlight_rect",
           "place_card")

from dataclasses import dataclass
from typing import Iterable, Optional

Rect = tuple[float, float, float, float]

CONFIG_SECTION = "client"


@dataclass(frozen=True)
class TourStep:
    """One coach mark. `target` names a spotlight the app resolves to live
    widgets; empty means a full scrim with the card centered. `compact_body`
    replaces `body` in Compact Mode when the controls differ there."""
    target: str
    title: str
    body: str
    compact_body: str = ""

    def text(self, compact: bool) -> str:
        return self.compact_body if compact and self.compact_body else self.body


LAUNCHER_TOUR = (
    TourStep("", "Welcome to MultiworldGG",
             "This quick tour shows how to get from here into a game. Whatever "
             "is highlighted stays clickable, so try things as you go."),
    TourStep("search", "Find your game",
             "Type a game's name here and press Enter to filter the list. The "
             "restore button clears the search and lists every installed game again.",
             "Type a game's name here and press Enter to see the matching games. "
             "The restore button clears the search and brings the play screen back."),
    TourStep("game_list", "Select the game",
             "Click a game in the list to select it. Its client, tools and setup "
             "guide fill in on the right.",
             "Click a game in the list to select it and return to the play screen."),
    TourStep("favorites", "Favorites",
             "Selected games show up on this bar. Click the heart on a game to "
             "keep it here, one click away next time."),
    TourStep("client_type", "Choose a client type",
             "Game Client is the default for a selected game. Text Client is chat "
             "and commands only, Universal Tracker adds location tracking, and "
             "Manual Client is for manual games."),
    TourStep("connection", "Enter the room details",
             "The server address, port, your slot name and the room password, if "
             "it has one. They are remembered for next time."),
    TourStep("launch", "Launch",
             "Opens the client for your selection in its own window. The launcher "
             "stays open, so you can launch more clients."),
    TourStep("menu", "Everything else",
             "Wondering where the other tools went? Start/Host Game, Generate, "
             "Patch, Install APWorld, Settings and Exit all live in this menu."),
)

CLIENT_TOUR = (
    TourStep("", "Welcome to the client",
             "This window is the client for your game. The console shows what "
             "happens in the multiworld, and the buttons along the bottom switch "
             "between screens."),
    TourStep("input", "Chat and commands",
             "This button slides up the text field. Type to chat with the other "
             "players, or start with / for client commands (/help lists them) and "
             "! for server commands such as !hint.",
             "Type here to chat with the other players, or start with / for client "
             "commands (/help lists them) and ! for server commands such as !hint."),
    TourStep("hint", "Hints",
             "The Hint button opens the hint table for your slot. Its own text "
             "field searches items and locations to ask for a new hint."),
    TourStep("nav", "More screens",
             "Games that bring their own views, like a tracker or a map, add their "
             "buttons to this row once you are connected."),
    TourStep("menu", "Menu",
             "Reconnect, Settings and Exit are in this menu."),
)

# Keyed by process role (mwgg_gui.constants ROLE_LAUNCHER / ROLE_CLIENT).
TOURS = {"launcher": LAUNCHER_TOUR, "client": CLIENT_TOUR}


def config_key(role: str) -> str:
    return f"onboarding_{role}"


def tour_pending(app_config, role: str) -> bool:
    """True until the role's tour was finished or skipped. Reads pass
    fallback=False: build_config never runs for a pre-existing client.ini,
    and an absent key means the tour has not been shown yet."""
    return not app_config.getboolean(CONFIG_SECTION, config_key(role), fallback=False)


def mark_tour_done(app_config, role: str) -> None:
    if not app_config.has_section(CONFIG_SECTION):
        app_config.add_section(CONFIG_SECTION)
    app_config.set(CONFIG_SECTION, config_key(role), "1")


def union_rect(rects: Iterable[Rect]) -> Optional[Rect]:
    """Bounding box of the rects, None for none."""
    rects = list(rects)
    if not rects:
        return None
    left = min(x for x, _y, _w, _h in rects)
    bottom = min(y for _x, y, _w, _h in rects)
    right = max(x + w for x, _y, w, _h in rects)
    top = max(y + h for _x, y, _w, h in rects)
    return left, bottom, right - left, top - bottom


def spotlight_rect(rect: Rect, pad: float, bounds: Rect) -> Rect:
    """`rect` grown by `pad` on every side and clipped to `bounds`."""
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    left = max(x - pad, bx)
    bottom = max(y - pad, by)
    right = min(x + w + pad, bx + bw)
    top = min(y + h + pad, by + bh)
    return left, bottom, max(right - left, 0), max(top - bottom, 0)


def place_card(card_size: tuple[float, float], bounds: Rect,
               target: Optional[Rect] = None, margin: float = 16.0) -> tuple[float, float]:
    """Bottom-left corner for the card: centered in `bounds` without a target,
    else below, above, right of, or left of the target, the first that fits,
    centered on the target as far as `bounds` allows. Y grows upward."""
    bx, by, bw, bh = bounds
    cw, ch = card_size
    centered = (bx + (bw - cw) / 2, by + (bh - ch) / 2)
    if target is None:
        return centered
    tx, ty, tw, th = target

    def clamp(value, low, high):
        return max(low, min(value, high))

    cx = clamp(tx + (tw - cw) / 2, bx + margin, bx + bw - cw - margin)
    cy = clamp(ty + (th - ch) / 2, by + margin, by + bh - ch - margin)
    if ty - margin - ch >= by:
        return cx, ty - margin - ch
    if ty + th + margin + ch <= by + bh:
        return cx, ty + th + margin
    if tx + tw + margin + cw <= bx + bw:
        return tx + tw + margin, cy
    if tx - margin - cw >= bx:
        return tx - margin - cw, cy
    return centered
