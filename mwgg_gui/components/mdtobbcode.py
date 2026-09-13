"""
Minimal markdown -> BBCode-markup label converter.

Targets the shape of GitHub release changelogs (headings, bullet lists,
bold, links, inline code), this is not exhaustive. Block-level elements
pick a theme font_style/role from mw_theme.py's registered font_styles;
inline elements become Kivy markup tags inside each label's text.
"""
from __future__ import annotations

__all__ = ("MarkdownBoxLayout",)

import re
from dataclasses import dataclass

from kivy.metrics import dp
from kivy.utils import escape_markup
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

# Descending by font-size (mw_theme.py RegisterFonts): Headline down through
# Title. H1 starts at Headline/large (32sp), H6 ends at Title/small (14sp).
HEADING_STYLES = {
    1: ("Headline", "large"),
    2: ("Headline", "medium"),
    3: ("Headline", "small"),
    4: ("Title", "large"),
    5: ("Title", "medium"),
    6: ("Title", "small"),
}
BODY_STYLE = ("Body", "medium")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM_RE = re.compile(r"^[*\-+]\s+(.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)|_([^_]+?)_")

_LINK_PLACEHOLDER = "\x00{}\x00"

@dataclass
class MarkupBlock:
    text: str
    font_style: str
    role: str
    list_item: bool = False

class MarkdownBoxLayout(MDBoxLayout):
    """A vertical MDBoxLayout of MDLabels from markdown text."""

    def __init__(self, markdown_text: str, **kwargs):
        super().__init__(**kwargs)
        self.spacing = dp(4)
        self.orientation = "vertical"
        self.adaptive_height = True

        for block in self.parse_markdown(markdown_text):
            label = MDLabel(
                text=block.text,
                markup=True,
                font_style=block.font_style,
                role=block.role,
                halign="left",
                valign="top",
                adaptive_height=True,
                padding=(dp(16) if block.list_item else 0, 0),
            )
            label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
            self.add_widget(label)

    @staticmethod
    def _inline_to_bbcode(text: str) -> str:
        """Convert one line's inline markdown (links, bold, italic, code) to
        Kivy markup. Links are pulled out before escaping (they use the same
        brackets escape_markup rewrites), then restored afterward."""
        links: list[tuple[str, str]] = []

        def _stash_link(match: re.Match) -> str:
            links.append((match.group(1), match.group(2)))
            return _LINK_PLACEHOLDER.format(len(links) - 1)

        text = _LINK_RE.sub(_stash_link, text)
        text = escape_markup(text)
        text = _CODE_RE.sub(lambda m: f"[font=Argon]{m.group(1)}[/font]", text)
        text = _BOLD_RE.sub(lambda m: f"[b]{m.group(1)}[/b]", text)
        text = _ITALIC_RE.sub(
            lambda m: f"[i]{m.group(1) or m.group(2)}[/i]", text
        )

        for index, (label, url) in enumerate(links):
            placeholder = _LINK_PLACEHOLDER.format(index)
            bbcode_link = f"[ref={escape_markup(url)}][u]{escape_markup(label)}[/u][/ref]"
            text = text.replace(placeholder, bbcode_link)
        return text

    def parse_markdown(self, markdown_text: str) -> list[MarkupBlock]:
        """Parse markdown into ordered blocks of BBCode text + font style/role.
        Blank lines are dropped; anything not a heading or bullet is a paragraph.
        """
        blocks: list[MarkupBlock] = []
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            heading_match = _HEADING_RE.match(stripped)
            if heading_match:
                level = len(heading_match.group(1))
                font_style, role = HEADING_STYLES[level]
                blocks.append(
                    MarkupBlock(self._inline_to_bbcode(heading_match.group(2)), font_style, role)
                )
                continue

            list_match = _LIST_ITEM_RE.match(stripped)
            if list_match:
                font_style, role = BODY_STYLE
                blocks.append(
                    MarkupBlock(
                        "• " + self._inline_to_bbcode(list_match.group(1)),
                        font_style, role, list_item=True,
                    )
                )
                continue

            font_style, role = BODY_STYLE
            blocks.append(MarkupBlock(self._inline_to_bbcode(stripped), font_style, role))
        return blocks
