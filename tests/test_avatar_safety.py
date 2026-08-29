"""Tests for mwgg_gui/components/avatar_safety.py, the avatar URL boundary.

avatar_safety only needs mwgg_gui.constants, so it is loaded by file path
with a stubbed constants module (bypassing mwgg_gui/__init__, which imports
the full Kivy GUI). Probe threads are replaced with a recorder so tests are
deterministic and make no network calls.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import urllib.error
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "mwgg_gui" / "components" / "avatar_safety.py"
)

TRUSTED_URL = "https://mw.prismativerse.com/avatar/abc.png"


def _load_avatar_safety(monkeypatch):
    pkg = types.ModuleType("mwgg_gui")
    constants = types.ModuleType("mwgg_gui.constants")
    constants.AVATAR_TOKEN_MINT_URL = "https://multiworld.gg/api/avatar/token"
    constants.AVATAR_UPLOAD_URL = "https://multiworld.gg/api/avatar/upload"
    constants.TRUSTED_AVATAR_HOSTS = ("multiworld.gg", "mw.prismativerse.com")
    monkeypatch.setitem(sys.modules, "mwgg_gui", pkg)
    monkeypatch.setitem(sys.modules, "mwgg_gui.constants", constants)
    spec = importlib.util.spec_from_file_location(
        "avatar_safety_under_test", _MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingThread:
    """Stands in for threading.Thread; records instead of running."""
    started = []

    def __init__(self, target=None, args=(), **kwargs):
        self.target = target
        self.args = args

    def start(self):
        _RecordingThread.started.append((self.target, self.args))


def _with_recorded_threads(module):
    _RecordingThread.started = []
    module.threading.Thread = _RecordingThread
    return _RecordingThread


def test_untrusted_urls_collapse_without_probing(monkeypatch):
    module = _load_avatar_safety(monkeypatch)
    threads = _with_recorded_threads(module)
    assert module.safe_avatar_source("") == ""
    assert module.safe_avatar_source("http://mw.prismativerse.com/a.png") == ""
    assert module.safe_avatar_source("https://evil.example/a.png") == ""
    assert threads.started == []


def test_unknown_trusted_url_passes_and_probes_once(monkeypatch):
    module = _load_avatar_safety(monkeypatch)
    threads = _with_recorded_threads(module)
    assert module.safe_avatar_source(TRUSTED_URL) == TRUSTED_URL
    assert module.safe_avatar_source(TRUSTED_URL) == TRUSTED_URL
    assert threads.started == [(module._probe_avatar, (TRUSTED_URL,))]


def test_failed_probe_collapses_later_calls(monkeypatch):
    module = _load_avatar_safety(monkeypatch)
    _with_recorded_threads(module)

    def _raise_404(*args, **kwargs):
        raise urllib.error.HTTPError(TRUSTED_URL, 404, "Not Found", None, None)

    module.request.urlopen = _raise_404
    module._probe_avatar(TRUSTED_URL)
    assert module._probe_results[TRUSTED_URL] is False
    assert module.safe_avatar_source(TRUSTED_URL) == ""


def test_successful_probe_keeps_url_and_stops_reprobing(monkeypatch):
    module = _load_avatar_safety(monkeypatch)
    threads = _with_recorded_threads(module)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return b"x"

    module.request.urlopen = lambda *args, **kwargs: _Resp()
    module._probe_avatar(TRUSTED_URL)
    assert module._probe_results[TRUSTED_URL] is True
    assert module.safe_avatar_source(TRUSTED_URL) == TRUSTED_URL
    assert threads.started == []
