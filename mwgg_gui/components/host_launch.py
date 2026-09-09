from __future__ import annotations
"""
Local server launch (the launcher's Start Local Server button).

MultiServer runs detached in a console window of its own: that window is the
server's command line, so its output is never piped. The loading overlay is fed
by following the log file the server opens instead.
"""
__all__ = (
    "READY_MARKER",
    "build_command",
    "server_env",
    "server_popen_kwargs",
    "list_server_logs",
    "watch_server",
)

import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping

READY_MARKER = "Hosting game at"
# BaseUtils.init_logging: logs/Server_<timestamp>.txt, records "[Server at <time>]: <message>".
_LOG_PREFIX = "Server_"
_RECORD = re.compile(r"^\[Server at [^\]]*\]: ")
_WINDOWS = sys.platform in ("win32", "cygwin", "msys")


def build_command(base_cmd, port=None, admin_password=None) -> list[str]:
    cmd = list(base_cmd)
    if port:
        cmd += ["--port", str(port)]
    if admin_password:
        cmd += ["--admin-password", admin_password]
    return cmd


def server_env(environ: Mapping[str, str], frozen: bool) -> dict[str, str]:
    # The launcher already ran the world updater; the server must not repeat it.
    env = {**environ, "SKIP_REQUIREMENTS_UPDATE": "1"}
    if not frozen:
        env["KIVY_NO_ARGS"] = "1"
    return env


def server_popen_kwargs() -> dict:
    """A console window of its own, outliving the launcher."""
    if _WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def list_server_logs(log_folder: str) -> set[str]:
    try:
        return {name for name in os.listdir(log_folder)
                if name.startswith(_LOG_PREFIX) and name.endswith(".txt")}
    except OSError:
        return set()


def _new_log(log_folder: str, known: set[str]) -> str | None:
    fresh = list_server_logs(log_folder) - known
    # Timestamped names sort chronologically.
    return os.path.join(log_folder, max(fresh)) if fresh else None


def _read_records(path: str, offset: int, pending: bytes) -> tuple[int, bytes, list[str]]:
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
    except OSError:
        return offset, pending, []
    *complete, pending = (pending + chunk).split(b"\n")
    messages = []
    for raw in complete:
        line = raw.decode("utf-8-sig", errors="replace").rstrip("\r")
        # Continuation lines (tracebacks) stay in the file.
        if _RECORD.match(line):
            messages.append(_RECORD.sub("", line))
    return offset + len(chunk), pending, messages


def watch_server(process, log_folder: str, known_logs: set[str], *,
                 on_line: Callable[[str], None], on_ready: Callable[[str], None],
                 on_exit: Callable[[int], None], on_timeout: Callable[[], None],
                 timeout: float = 120.0, poll: float = 0.25,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
    """Follow the server's new log until it reports hosting, exits, or `timeout` passes.

    Blocking; run it on a worker thread. `known_logs` is list_server_logs() from
    before the spawn, so an earlier run's file is never mistaken for this one.
    """
    deadline = clock() + timeout
    log_path = None
    offset, pending = 0, b""
    while True:
        code = process.poll()
        if log_path is None:
            log_path = _new_log(log_folder, known_logs)
        if log_path is not None:
            offset, pending, messages = _read_records(log_path, offset, pending)
            for message in messages:
                on_line(message)
                if READY_MARKER in message:
                    on_ready(message)
                    return
        if code is not None:
            on_exit(code)
            return
        if clock() >= deadline:
            on_timeout()
            return
        sleep(poll)
