"""Shared fixtures for the GUI-side unit tests.

Run with the beta venv's python -- it has PyYAML and the beta core wheel
set installed:

    cd C:/Users/Lindsay/source/repos/mwgg-gui
    <MultiworldGG>/src/.venv/Scripts/python.exe -m pytest tests -q

The modules under test (world_data.py, yaml_io.py) import zero Kivy, but
the mwgg_gui package __init__ pulls in the whole GUI including Kivy's
Window -- so tests load them by file path via importlib and never import
the package.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_YAML_CREATOR = _REPO_ROOT / "mwgg_gui" / "yaml_creator"

# The beta monorepo checkout (BaseUtils and friends). Sibling layout by
# default; override with MWGG_BETA_SRC when the repos live elsewhere.
_BETA_SRC = Path(
    os.environ.get("MWGG_BETA_SRC", _REPO_ROOT.parent / "MultiworldGG" / "src")
)

if _BETA_SRC.is_dir() and str(_BETA_SRC) not in sys.path:
    sys.path.insert(0, str(_BETA_SRC))


def _load_by_path(name: str, filename: str):
    """Load a yaml_creator module by file path, bypassing mwgg_gui/__init__
    (which imports the full Kivy GUI)."""
    path = _YAML_CREATOR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def world_data():
    pytest.importorskip(
        "BaseUtils",
        reason="beta core not importable - set MWGG_BETA_SRC to the "
               "MultiworldGG/src checkout or run under the beta venv",
    )
    return _load_by_path("yaml_creator_world_data", "world_data.py")


@pytest.fixture(scope="session")
def yaml_io():
    pytest.importorskip(
        "yaml", reason="PyYAML not installed - run under the beta venv"
    )
    return _load_by_path("yaml_creator_yaml_io", "yaml_io.py")


@pytest.fixture(scope="session")
def weighted_model():
    return _load_by_path("yaml_creator_weighted_model", "weighted_model.py")
