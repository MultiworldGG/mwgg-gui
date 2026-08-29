"""Tests for mwgg_gui/launcher/setup_guide.py.

The module is Kivy-free but lives under the package, so it is loaded by file
path here (mwgg_gui/__init__ imports the full GUI). Its only package import,
mwgg_gui.constants, is stubbed so the load stays import-light; the core-only
imports (Utils, ModuleUpdate) are function-local in the module and never run
in these tests.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import zipfile
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "mwgg_gui" / "launcher" / "setup_guide.py"
)


@pytest.fixture(scope="module")
def setup_guide():
    constants = types.ModuleType("mwgg_gui.constants")
    constants.SETUP_GUIDE_URL = "https://example.test/learn/en/tutorial/{game}/setup"
    saved = {name: sys.modules.get(name) for name in ("mwgg_gui", "mwgg_gui.constants")}
    sys.modules["mwgg_gui"] = types.ModuleType("mwgg_gui")
    sys.modules["mwgg_gui.constants"] = constants
    try:
        spec = importlib.util.spec_from_file_location(
            "setup_guide_under_test", _MODULE_PATH
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("setup_guide_under_test", None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _archive(tmp_path: Path, *members: str) -> zipfile.ZipFile:
    path = tmp_path / "world.apworld"
    with zipfile.ZipFile(path, "w") as zf:
        for member in members:
            zf.writestr(member, f"# {member}")
    return zipfile.ZipFile(path)


def test_url_percent_encodes_the_game_name(setup_guide):
    assert setup_guide.setup_guide_url("Kingdom Hearts II") == (
        "https://example.test/learn/en/tutorial/Kingdom%20Hearts%20II/setup"
    )


def test_url_keeps_the_game_name_to_one_path_segment(setup_guide):
    assert setup_guide.setup_guide_url("Pokemon Red/Blue").endswith(
        "Pokemon%20Red%2FBlue/setup"
    )


def test_finds_setup_doc_under_the_module_directory(setup_guide, tmp_path):
    with _archive(tmp_path, "khddd/docs/credits.md", "khddd/docs/setup.md") as archive:
        assert setup_guide.find_setup_doc(archive) == "khddd/docs/setup.md"


def test_finds_setup_doc_under_a_wheel_layout(setup_guide, tmp_path):
    with _archive(tmp_path, "worlds/kh3/docs/setup_en.md") as archive:
        assert setup_guide.find_setup_doc(archive) == "worlds/kh3/docs/setup_en.md"


def test_prefers_the_english_doc(setup_guide, tmp_path):
    with _archive(tmp_path, "w/docs/setup_de.md", "w/docs/setup_en.md",
                  "w/docs/setup.md") as archive:
        assert setup_guide.find_setup_doc(archive) == "w/docs/setup_en.md"


def test_falls_back_to_a_localized_doc(setup_guide, tmp_path):
    with _archive(tmp_path, "w/docs/setup_fr.md") as archive:
        assert setup_guide.find_setup_doc(archive) == "w/docs/setup_fr.md"


def test_no_setup_doc_returns_none(setup_guide, tmp_path):
    with _archive(tmp_path, "w/docs/credits.md", "w/__init__.py",
                  "w/setup.md") as archive:
        assert setup_guide.find_setup_doc(archive) is None


def test_ignores_docs_subdirectories(setup_guide, tmp_path):
    with _archive(tmp_path, "w/docs/images/setup.md") as archive:
        assert setup_guide.find_setup_doc(archive) is None


def test_extract_writes_the_doc_and_returns_its_path(setup_guide, tmp_path,
                                                     monkeypatch):
    archive_path = tmp_path / "khddd.apworld"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("khddd/docs/setup.md", "# Setup")
    monkeypatch.setattr(setup_guide, "find_custom_world_archive",
                        lambda module: archive_path)
    monkeypatch.setattr(setup_guide.tempfile, "gettempdir", lambda: str(tmp_path))

    doc_path = setup_guide.extract_bundled_setup_doc("khddd")

    assert os.path.basename(doc_path) == "khddd_setup.md"
    assert Path(doc_path).read_text(encoding="utf-8") == "# Setup"


def test_extract_returns_none_without_an_archive(setup_guide, monkeypatch):
    monkeypatch.setattr(setup_guide, "find_custom_world_archive", lambda module: None)
    assert setup_guide.extract_bundled_setup_doc("nothing_installed") is None
