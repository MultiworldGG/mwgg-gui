"""Pure hint-visibility logic shared by the classic and new hint screens.

Deliberately import-light (no kivy) so tests load it by file path, same as
columns.py.
"""
from __future__ import annotations

import typing


def resolve_ui_hint_bucket(hint: dict, slot_concerns_self: typing.Callable[[int], bool]) -> typing.Optional[int]:
    """The app.ui_hint_data bucket key ("other player") for a raw server hint dict.

    Mirrors MultiMDApp.refresh_hints's own bucketing so a hint row resolves to
    the same UIHint the new hint screen's hide checkbox edits. Returns None if
    neither side of the hint concerns this slot (should not happen for rows
    coming from ``_read_hints_{team}_{slot}``).
    """
    if slot_concerns_self(hint["receiving_player"]):
        return hint["finding_player"]
    if slot_concerns_self(hint["finding_player"]):
        return hint["receiving_player"]
    return None


def row_is_visible(hidden: bool, show_all: bool) -> bool:
    """Whether a hint row should render, matching the new screen's ``not hint.hide or show_all``."""
    return show_all or not hidden
