"""Branding regression guard.

The product name is "MultiworldGG" (lowercase w); built exe names derive
from BaseUtils.FROZEN_TARGETS in the monorepo, which uses the same form.
The needle is concatenated so this file does not flag itself.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SUFFIXES = {".py", ".kv", ".md", ".toml", ".yml"}
_SKIP_DIRS = {".venv", ".git", "__pycache__", ".claude", "mwgg_gui.egg-info"}
_WRONG = "MultiWorld" + "GG"


def test_no_wrong_case_brand_name():
    offenders = []
    for path in _REPO_ROOT.rglob("*"):
        if path.suffix not in _SUFFIXES or not path.is_file():
            continue
        if _SKIP_DIRS.intersection(p.name for p in path.parents):
            continue
        if _WRONG in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []
