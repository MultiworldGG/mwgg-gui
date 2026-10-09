"""Swap text colors in console markup that was already rendered."""
from __future__ import annotations

import re
from typing import Mapping

from NetUtils import bbcode_gradient

__all__ = ("recolor_markup",)

_TAG = re.compile(r"\[color=([0-9A-Fa-f]{6})\]")
_GLYPH = re.compile(r"\[color=([0-9A-Fa-f]{6})\](&(?:bl|br|amp);|\S)\[/color\]")
_GLYPH_RUN = r"\[color=[0-9A-Fa-f]{6}\](?:&(?:bl|br|amp);|\S)\[/color\]"
# Two or more single-glyph tags may be one bbcode_gradient; runs stop at line breaks.
_RECOLOR = re.compile(
    rf"(?P<run>{_GLYPH_RUN}(?:[^\S\n]*{_GLYPH_RUN})+)|\[color=(?P<hex>[0-9A-Fa-f]{{6}})\]"
)


def recolor_markup(markup: str, remap: Mapping[str, str]) -> str:
    """Rewrite the color tags whose hex is a key of remap.

    A run that is exactly a NetUtils.bbcode_gradient between its first and
    last colors is regenerated from the remapped end colors, so its
    interpolated middle follows too.

    Args:
        markup: Kivy markup, possibly many lines.
        remap: Lowercase old hex to new hex, both without '#'.
    """
    if not remap:
        return markup

    def swap(hex_color: str) -> str:
        return remap.get(hex_color.lower(), hex_color)

    def recolor(match: re.Match) -> str:
        run = match.group("run")
        if run is None:
            return f"[color={swap(match.group('hex'))}]"
        glyphs = _GLYPH.findall(run)
        start, end = glyphs[0][0], glyphs[-1][0]
        text = _GLYPH.sub(r"\2", run)
        if bbcode_gradient(start, end, text) != run:
            return _TAG.sub(lambda tag: f"[color={swap(tag.group(1))}]", run)
        return bbcode_gradient(swap(start), swap(end), text)

    return _RECOLOR.sub(recolor, markup)
