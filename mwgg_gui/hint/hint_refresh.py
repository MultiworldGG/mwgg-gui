"""Kivy-free change detection for the hint screen and slots sidebar.

Both rebuild their widget trees from scratch on every ``MultiMDApp.update_hints``
call, and the Universal Tracker overlay re-fires that call on every scout
reply, so the app skips the rebuild when the rendered inputs are unchanged.
"""
from __future__ import annotations

import json
import typing


def _hint_order(hint: dict) -> tuple:
    return (hint.get("finding_player", 0), hint.get("location", 0))


def render_signature(hints: typing.Iterable[dict], mwgg_hints: dict, profiles: dict,
                     names_loaded: bool, extra_columns: typing.Iterable[typing.Any] = ()) -> str:
    """Digest of everything the hint table and slots sidebar draw from.

    ``extra_columns`` are registered hint-table columns (``key`` +
    ``build_value(hint, row)``); their values come from state outside the hint
    dicts (the tracker's in-logic set), so they are rebuilt into the digest.
    Hint order is normalised: the server serialises a set.
    """
    ordered = sorted(hints, key=_hint_order)
    columns = []
    for column in extra_columns:
        values = []
        for hint in ordered:
            row: dict = {}
            column.build_value(hint, row)
            values.append(row.get(column.key))
        columns.append((column.key, values))
    return json.dumps([ordered, mwgg_hints, profiles, bool(names_loaded), columns],
                      sort_keys=True, default=str)
