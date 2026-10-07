"""Vsync wait after the swap, GIL released (components/flip_sync.py).

flip_sync.py imports Kivy and layout_mode at module level, so it is loaded by
file path with those imports stubbed; the `env` fixture then swaps in a fake
window, config, GL backend and GL functions. The last test makes
real blocking C calls through the module's own prototype to check the GIL is
released.
"""
from __future__ import annotations

import configparser
import ctypes
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "flip_sync.py"
_CLEAR, _FINISH = 0x1100, 0x1200
_SYNC = [("clear", 0x4000), ("finish",)]


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def flip_sync():
    """The module as loaded, its Kivy and layout_mode names still placeholders."""
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.config": _stub("kivy.config", Config=None),
        "kivy.core": _stub("kivy.core"),
        "kivy.core.window": _stub("kivy.core.window", Window=None),
        "kivy.core.window.window_sdl2": _stub("kivy.core.window.window_sdl2", WindowSDL=None),
        "kivy.graphics": _stub("kivy.graphics"),
        "kivy.graphics.cgl": _stub("kivy.graphics.cgl", cgl_get_initialized_backend_name=None),
        "kivy.logger": _stub("kivy.logger", Logger=None),
        "mwgg_gui": _stub("mwgg_gui"),
        "mwgg_gui.components": _stub("mwgg_gui.components"),
        "mwgg_gui.components.layout_mode": _stub("mwgg_gui.components.layout_mode", _loaded_sdl=None),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("flip_sync_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


@pytest.fixture
def env(flip_sync):
    """An SDL window on Linux with the sdl2 GL backend; `calls` logs swaps and GL calls."""
    env = types.SimpleNamespace(
        module=flip_sync, backend="sdl2",
        calls=[], lookups=[], wrapped=[], warnings=[],
        addresses={b"glClear": _CLEAR, b"glFinish": _FINISH}, failing={})

    class WindowSDL:
        def flip(self):
            env.calls.append("swap")

    def get_proc_address(name):
        env.lookups.append(name)
        return env.addresses[name]

    def gl_function(address, *argtypes):
        env.wrapped.append((address, argtypes))
        name = {_CLEAR: "clear", _FINISH: "finish"}.get(address, address)

        def call(*args):
            env.calls.append((name, *args))
            if name in env.failing:
                raise env.failing[name]
        return call

    env.config = configparser.ConfigParser()
    env.config["graphics"] = {"sync_after_flip": "1"}
    env.get_proc_address, env.WindowSDL, env.window = get_proc_address, WindowSDL, WindowSDL()
    flip_sync.sys = types.SimpleNamespace(platform="linux")
    flip_sync.Config = env.config
    flip_sync.Window, flip_sync.WindowSDL = env.window, WindowSDL
    flip_sync.cgl_get_initialized_backend_name = lambda: env.backend
    flip_sync.Logger = types.SimpleNamespace(warning=lambda msg, *args: env.warnings.append(msg % args))
    flip_sync._loaded_sdl = lambda: types.SimpleNamespace(SDL_GL_GetProcAddress=get_proc_address)
    flip_sync._gl_function = gl_function
    return env


@pytest.mark.parametrize("value", ["0", "off", "maybe", "", None])
def test_config_off_or_unparsable_leaves_flip_alone(env, value):
    if value is None:
        env.config.remove_option("graphics", "sync_after_flip")
    else:
        env.config.set("graphics", "sync_after_flip", value)
    original = env.WindowSDL.flip
    env.module.install_flip_sync()
    assert env.WindowSDL.flip is original
    assert env.module.flip_sync_state() == "off"


def test_non_sdl_window_and_mock_backend_leave_flip_alone(env):
    original = env.WindowSDL.flip
    env.module.Window = object()
    env.module.install_flip_sync()
    env.module.Window, env.backend = env.window, "mock"
    env.module.install_flip_sync()
    assert env.WindowSDL.flip is original
    assert env.module.flip_sync_state() == "off"


def test_flip_swaps_then_clears_and_finishes(env):
    env.module.install_flip_sync()
    env.window.flip()
    env.window.flip()
    assert env.calls == ["swap", *_SYNC, "swap", *_SYNC]
    assert env.warnings == []


def test_install_is_idempotent(env):
    env.module.install_flip_sync()
    patched = env.WindowSDL.flip
    env.module.install_flip_sync()
    assert env.WindowSDL.flip is patched
    env.window.flip()
    assert env.calls == ["swap", *_SYNC]


def test_gl_functions_resolve_once_on_the_first_flip(env):
    assert env.module.flip_sync_state() == "off"
    env.module.install_flip_sync()
    assert env.module.flip_sync_state() == "pending"
    assert (env.lookups, env.wrapped) == ([], [])

    for _ in range(3):
        env.window.flip()
    assert env.module.flip_sync_state() == "on"
    assert env.lookups == [b"glClear", b"glFinish"]
    assert (env.get_proc_address.restype, env.get_proc_address.argtypes) == (
        ctypes.c_void_p, (ctypes.c_char_p,))
    assert env.wrapped == [(_CLEAR, (ctypes.c_uint,)), (_FINISH, ())]


@pytest.mark.parametrize("backend", ["glew", "sdl2"])
def test_windows_takes_gl_from_opengl32_exports(env, monkeypatch, backend):
    dlls = []

    def win_dll(name):
        dlls.append(name)
        return types.SimpleNamespace(glClear=ctypes.c_void_p(_CLEAR), glFinish=ctypes.c_void_p(_FINISH))

    monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)
    env.module.sys.platform, env.backend = "win32", backend
    env.module.install_flip_sync()
    env.window.flip()
    assert env.calls == ["swap", *_SYNC]
    assert (dlls, env.lookups) == (["opengl32"], [])
    assert env.wrapped == [(_CLEAR, (ctypes.c_uint,)), (_FINISH, ())]


def test_angle_is_reported_unavailable(env):
    original = env.WindowSDL.flip
    env.module.sys.platform, env.backend = "win32", "angle_sdl2"
    env.module.install_flip_sync()
    assert env.WindowSDL.flip is original
    assert env.module.flip_sync_state() == "unavailable (ANGLE renders through Direct3D)"


def _lookup_null(env):
    env.addresses[b"glFinish"] = None


def _lookup_without_sdl(env):
    def no_sdl():
        raise OSError("SDL2 not loaded")
    env.module._loaded_sdl = no_sdl


@pytest.mark.parametrize("break_lookup, error", [
    (_lookup_null, "LookupError('SDL_GL_GetProcAddress returned NULL')"),
    (_lookup_without_sdl, "OSError('SDL2 not loaded')"),
])
def test_lookup_failure_stops_syncing_and_warns_once(env, break_lookup, error):
    break_lookup(env)
    env.module.install_flip_sync()
    env.window.flip()
    env.window.flip()
    assert env.calls == ["swap", "swap"]
    assert env.module.flip_sync_state() == f"unavailable (GL lookup failed: {error})"
    assert env.warnings == [f"FlipSync: off for this session, GL lookup failed: {error}"]


@pytest.mark.parametrize("failing, synced", [("clear", _SYNC[:1]), ("finish", _SYNC)])
def test_gl_call_error_stops_syncing_and_warns_once(env, failing, synced):
    env.failing[failing] = OSError("exception: access violation reading 0x0000000000000001")
    env.module.install_flip_sync()
    env.window.flip()
    env.window.flip()
    assert env.calls == ["swap", *synced, "swap"]
    assert env.module.flip_sync_state() == (
        "unavailable (GL call failed: exception: access violation reading 0x0000000000000001)")
    assert env.warnings == [
        "FlipSync: off for this session, "
        "GL call failed: exception: access violation reading 0x0000000000000001"]


def _blocking_c_function() -> tuple[int, int]:
    """(address, units per ms) of a C function that blocks for its unsigned argument."""
    if sys.platform == "win32":
        return ctypes.cast(ctypes.windll.kernel32.Sleep, ctypes.c_void_p).value, 1
    return ctypes.cast(ctypes.CDLL(None).usleep, ctypes.c_void_p).value, 1000


def _spins_during(call, *args) -> int:
    """How far a second Python thread counts while `call(*args)` runs."""
    count, running, started = 0, True, threading.Event()

    def spin():
        nonlocal count
        started.set()
        while running:
            count += 1

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    started.wait()
    try:
        before = count
        call(*args)
        after = count
    finally:
        running = False
        thread.join()
    return after - before


@pytest.mark.skipif(not getattr(sys, "_is_gil_enabled", lambda: True)(), reason="no GIL to release")
def test_gl_prototype_releases_the_gil_while_the_call_blocks(flip_sync):
    address, per_ms = _blocking_c_function()
    released_call = flip_sync._gl_function(address, ctypes.c_uint)
    held_call = ctypes.PYFUNCTYPE(None, ctypes.c_uint)(address)
    # Far longer than the call (and Windows' ~16 ms wait granularity): the
    # counter cannot ask for the GIL while a held call blocks, so it shows no
    # progress.
    interval = sys.getswitchinterval()
    sys.setswitchinterval(0.25)
    try:
        released = _spins_during(released_call, 20 * per_ms)
        held = _spins_during(held_call, 20 * per_ms)
    finally:
        sys.setswitchinterval(interval)
    assert released > 1000
    assert released > 10 * held
