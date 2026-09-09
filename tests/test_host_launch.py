"""Local server launch helpers (components/host_launch.py); Kivy-free, loaded by file path."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "host_launch.py"


@pytest.fixture(scope="module")
def host_launch():
    spec = importlib.util.spec_from_file_location("host_launch_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


class _Process:
    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


def _record(message: str) -> bytes:
    return f"[Server at 2026-09-08 20:15:01,042]: {message}\n".encode()


def _watch(host_launch, process, log_folder, known, *, sleep, timeout=120.0, ticks=None):
    events = []
    now = iter(ticks or range(10_000))
    host_launch.watch_server(
        process, str(log_folder), known,
        on_line=lambda line: events.append(("line", line)),
        on_ready=lambda line: events.append(("ready", line)),
        on_exit=lambda code: events.append(("exit", code)),
        on_timeout=lambda: events.append(("timeout",)),
        timeout=timeout, poll=0, clock=lambda: next(now), sleep=sleep)
    return events


def test_build_command_appends_only_the_given_options(host_launch):
    base = ["C:/apps/MultiworldGGServer.exe"]
    assert host_launch.build_command(base) == base
    assert host_launch.build_command(base, port="38281", admin_password="hunter2") == [
        *base, "--port", "38281", "--admin-password", "hunter2"]
    assert host_launch.build_command(base, port=None, admin_password="") == base


def test_server_env_skips_the_updater_and_kivy_args_from_source(host_launch):
    assert host_launch.server_env({"PATH": "x"}, frozen=True) == {"PATH": "x", "SKIP_REQUIREMENTS_UPDATE": "1"}
    assert host_launch.server_env({"PATH": "x"}, frozen=False)["KIVY_NO_ARGS"] == "1"


def test_server_gets_its_own_console(host_launch):
    kwargs = host_launch.server_popen_kwargs()
    if sys.platform.startswith("win"):
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    else:
        assert kwargs == {"start_new_session": True}


def test_only_server_logs_are_listed(host_launch, tmp_path):
    (tmp_path / "Server_2026_09_08_20_00_00.txt").write_text("")
    (tmp_path / "Client_2026_09_08_20_00_00.txt").write_text("")
    assert host_launch.list_server_logs(str(tmp_path)) == {"Server_2026_09_08_20_00_00.txt"}
    assert host_launch.list_server_logs(str(tmp_path / "missing")) == set()


def test_watch_follows_the_new_log_until_hosting(host_launch, tmp_path):
    hosting = "Hosting game at 1.2.3.4:38281 (No password)"
    (tmp_path / "Server_2026_09_08_19_00_00.txt").write_bytes(_record(hosting))
    known = host_launch.list_server_logs(str(tmp_path))
    new = tmp_path / "Server_2026_09_08_20_00_00.txt"
    writes = iter([
        lambda: new.write_bytes(b"\xef\xbb\xbf" + _record("Loading multidata")),
        lambda: new.open("ab").write(b"Traceback line without prefix\n" + _record(hosting)),
    ])

    def sleep(_):
        next(writes, lambda: None)()

    events = _watch(host_launch, _Process(), tmp_path, known, sleep=sleep)
    assert events == [("line", "Loading multidata"), ("line", hosting), ("ready", hosting)]


def test_watch_reports_exit_after_draining_the_log(host_launch, tmp_path):
    process = _Process()
    new = tmp_path / "Server_2026_09_08_20_00_00.txt"

    def sleep(_):
        new.write_bytes(_record("No file selected. Exiting."))
        process.returncode = 1

    events = _watch(host_launch, process, tmp_path, set(), sleep=sleep)
    assert events == [("line", "No file selected. Exiting."), ("exit", 1)]


def test_watch_times_out_when_the_server_never_reports(host_launch, tmp_path):
    events = _watch(host_launch, _Process(), tmp_path, set(), sleep=lambda _: None,
                    timeout=5, ticks=[0, 1, 3, 5, 7])
    assert events == [("timeout",)]
