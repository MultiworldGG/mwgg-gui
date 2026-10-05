"""mwgg_gui/__init__.py must pin Kivy's env before its first kivy import (parsed, never imported)."""
import ast
from pathlib import Path

_INIT = Path(__file__).resolve().parent.parent / "mwgg_gui" / "__init__.py"


def _is_kivy_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".")[0] == "kivy"
    return isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "kivy" for alias in node.names)


def _sets_default(node: ast.stmt, key: str) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "attr", None) == "setdefault"
            and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == key)


def test_kivy_env_pinned_before_first_kivy_import():
    body = ast.parse(_INIT.read_text(encoding="utf-8")).body
    first_kivy = next(i for i, node in enumerate(body) if _is_kivy_import(node))
    for key in ("KIVY_HOME", "KIVY_DATA_DIR"):
        assert any(_sets_default(node, key) for node in body[:first_kivy]), key
