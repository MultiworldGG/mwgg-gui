"""Local server launch helpers (components/host_launch.py); Kivy-free, loaded by file path."""
from __future__ import annotations

import importlib.util
import logging
import os
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


def _record(message: str, name: str = "root") -> bytes:
    """One line as BaseUtils.init_logging's file handler writes it."""
    formatter = logging.Formatter("[%(name)s at %(asctime)s]: %(message)s")
    record = logging.LogRecord(name, logging.INFO, __file__, 0, message, None, None)
    return (formatter.format(record) + "\n").encode()


def _init_record(pid: int) -> bytes:
    """The record BaseUtils.init_logging opens every log with."""
    return _record(f"MultiworldGG (0.9.3) logging initialized on Windows-11 process {pid}"
                   f" running Python 3.13.15 (frozen)")


def _watch(host_launch, log_folder, known, *, sleep, timeout=120.0, ticks=None,
           alive=lambda pid: True):
    events = []
    now = iter(ticks or range(10_000))
    host_launch.watch_server(
        str(log_folder), known,
        on_line=lambda line: events.append(("line", line)),
        on_ready=lambda line: events.append(("ready", line)),
        on_exit=lambda: events.append(("exit",)),
        on_timeout=lambda: events.append(("timeout",)),
        timeout=timeout, poll=0, clock=lambda: next(now), sleep=sleep, alive=alive)
    return events


def test_build_command_appends_only_the_given_options(host_launch):
    base = ["C:/apps/MultiworldGGServer.exe"]
    assert host_launch.build_command(base) == base
    assert host_launch.build_command(base, port="38281", admin_password="hunter2") == [
        *base, "--port", "38281", "--admin-password", "hunter2"]
    assert host_launch.build_command(base, port=None, admin_password="") == base


def test_server_env_skips_the_updater_and_kivy_args_from_source(host_launch):
    assert host_launch.server_env(frozen=True) == {"SKIP_REQUIREMENTS_UPDATE": "1"}
    assert host_launch.server_env(frozen=False)["KIVY_NO_ARGS"] == "1"


def test_server_alive_tracks_a_real_process(host_launch):
    """The launcher holds no handle on a terminal tab's child, so this reads the OS."""
    assert host_launch.server_alive(os.getpid()) is True
    done = subprocess.Popen([sys.executable, "-c", ""])
    done.wait()
    assert host_launch.server_alive(done.pid) is False


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
    listening = "server listening on [::]:38281"
    writes = iter([
        lambda: new.write_bytes(b"\xef\xbb\xbf" + _record("Loading multidata")),
        lambda: new.open("ab").write(_record(listening, name="websockets.server")
                                     + b"Traceback line without prefix\n" + _record(hosting)),
    ])

    def sleep(_):
        next(writes, lambda: None)()

    events = _watch(host_launch, tmp_path, known, sleep=sleep)
    assert events == [("line", "Loading multidata"), ("line", listening),
                      ("line", hosting), ("ready", hosting)]


def test_watch_reports_exit_after_draining_the_log(host_launch, tmp_path):
    """The PID comes from the log; the last records land before the exit is reported."""
    running = {7656}
    new = tmp_path / "Server_2026_09_08_20_00_00.txt"
    new.write_bytes(_init_record(7656))

    def sleep(_):
        with new.open("ab") as fh:
            fh.write(_record("No file selected. Exiting."))
        running.clear()

    events = _watch(host_launch, tmp_path, set(), sleep=sleep, alive=lambda pid: pid in running)
    assert events[1:] == [("line", "No file selected. Exiting."), ("exit",)]


def test_watch_ignores_a_pid_it_never_saw(host_launch, tmp_path):
    """A log without the opening record must not end the watch on a dead PID guess."""
    (tmp_path / "Server_2026_09_08_20_00_00.txt").write_bytes(_record("Loading multidata"))
    events = _watch(host_launch, tmp_path, set(), sleep=lambda _: None, timeout=5,
                    ticks=[0, 1, 5], alive=lambda pid: False)
    assert events == [("line", "Loading multidata"), ("timeout",)]


def test_watch_times_out_when_the_server_never_reports(host_launch, tmp_path):
    events = _watch(host_launch, tmp_path, set(), sleep=lambda _: None,
                    timeout=5, ticks=[0, 1, 3, 5, 7])
    assert events == [("timeout",)]
