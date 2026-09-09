from __future__ import annotations
"""
Local server launch (the launcher's Start Local Server button).

MultiServer runs in a terminal window of its own -- that window is the server's
command line, so its output is never piped -- and BaseUtils.launch_exe puts it in
the same terminal the launcher's other CLI components use. The loading overlay is
fed by following the log file the server opens instead, and the PID that log
opens with stands in for the process handle a tab hand-off never gives back.
"""
__all__ = (
    "READY_MARKER",
    "build_command",
    "server_env",
    "list_server_logs",
    "server_alive",
    "watch_server",
)

import functools
import os
import re
import sys
import time
from collections.abc import Callable

READY_MARKER = "Hosting game at"
# BaseUtils.init_logging: logs/Server_<timestamp>.txt, records "[<logger> at <time>]: <message>".
# The logger name is the record's own (root, websockets.server, ...); "Server" only names the file.
_LOG_PREFIX = "Server_"
_RECORD = re.compile(r"^\[[^\]]+ at \d{4}-\d\d-\d\d[^\]]*\]: ")
# init_logging opens every log with "... logging initialized on <platform> process <pid> running ...".
_PID = re.compile(r"logging initialized\b.*\bprocess (\d+)\b")
_WINDOWS = sys.platform in ("win32", "cygwin", "msys")


def build_command(base_cmd, port=None, admin_password=None) -> list[str]:
    cmd = list(base_cmd)
    if port:
        cmd += ["--port", str(port)]
    if admin_password:
        cmd += ["--admin-password", admin_password]
    return cmd


def server_env(frozen: bool) -> dict[str, str]:
    """Variables the server needs on top of the launcher's own environment."""
    # The launcher already ran the world updater; the server must not repeat it.
    env = {"SKIP_REQUIREMENTS_UPDATE": "1"}
    if not frozen:
        env["KIVY_NO_ARGS"] = "1"
    return env


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


@functools.cache
def _kernel32():
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # a HANDLE truncates through the default int restype
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    return kernel32


def server_alive(pid: int) -> bool:
    """Whether the server is still running. It is the terminal's child, not ours,
    so liveness comes from the PID it logged rather than from a Popen object."""
    if _WINDOWS:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        kernel32 = _kernel32()
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            # a handle still open elsewhere outlives the process, so ask for the exit code
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def watch_server(log_folder: str, known_logs: set[str], *,
                 on_line: Callable[[str], None], on_ready: Callable[[str], None],
                 on_exit: Callable[[], None], on_timeout: Callable[[], None],
                 timeout: float = 120.0, poll: float = 0.25,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 alive: Callable[[int], bool] = server_alive) -> None:
    """Follow the server's new log until it reports hosting or its process ends.

    Blocking; run it on a worker thread. `known_logs` is list_server_logs() from
    before the launch, so an earlier run's file is never mistaken for this one.
    `timeout` is when the caller is told the server is taking its time: a server
    that has reported in is then followed for as long as it lives, because one
    sitting on its file picker is healthy and the wait is the user's own.
    """
    deadline = clock() + timeout
    log_path = None
    pid = None
    offset, pending = 0, b""
    while True:
        # checked before the read: everything a dead server wrote is already in the file
        exited = pid is not None and not alive(pid)
        if log_path is None:
            log_path = _new_log(log_folder, known_logs)
        if log_path is not None:
            offset, pending, messages = _read_records(log_path, offset, pending)
            for message in messages:
                on_line(message)
                if pid is None:
                    found = _PID.search(message)
                    if found:
                        pid = int(found.group(1))
                if READY_MARKER in message:
                    on_ready(message)
                    return
        if exited:
            on_exit()
            return
        if deadline is not None and clock() >= deadline:
            on_timeout()
            if pid is None:
                return
            deadline = None
        sleep(poll)
