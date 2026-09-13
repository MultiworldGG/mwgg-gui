from __future__ import annotations
"""
Generate launch (the launcher's Generate button).

Generate runs hidden with its output piped into the launcher log. Its stdin is
closed so a "Press enter" prompt can never wait on a hidden console, stderr is
drained on a thread of its own so a long traceback cannot fill that pipe while
stdout is being read, and a watchdog kills a process that has stopped writing
and stopped using CPU -- one blocked on a prompt or a pipe rather than working.
"""
__all__ = (
    "IDLE_TIMEOUT",
    "GenerateResult",
    "generate_env",
    "run_generate",
    "tree_cpu_seconds",
)

import functools
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

# Generate hands real work to children (a venv python.exe is a stub around the
# interpreter; uv installs a world), so quiet means the whole tree is quiet.
IDLE_TIMEOUT = 300.0
_WINDOWS = sys.platform in ("win32", "cygwin", "msys")


def generate_env(frozen: bool) -> dict[str, str]:
    """Variables Generate needs on top of the launcher's own environment."""
    # PYTHONIOENCODING keeps the piped output UTF-8 whatever the locale; the
    # launcher already ran the world updater, so Generate must not repeat it.
    env = {"PYTHONIOENCODING": "utf-8", "SKIP_REQUIREMENTS_UPDATE": "1"}
    if not frozen:
        env["KIVY_NO_ARGS"] = "1"
    return env


@dataclass
class GenerateResult:
    returncode: int | None
    killed: bool = False
    idle_seconds: float = 0.0
    stderr: str = ""
    tail: list[str] = field(default_factory=list)

    def error_message(self) -> str:
        if self.killed:
            return (f"Generate stopped responding: no output and no CPU use for {int(self.idle_seconds)} seconds,"
                    " so it was killed. See the logs folder.")
        detail = self.stderr.strip() or "\n".join(self.tail).strip() or "Unknown error"
        return f"Generation failed with code {self.returncode}:\n{detail}"


@functools.cache
def _kernel32():
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # a HANDLE truncates through the default int restype
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = (ctypes.c_ulong, ctypes.c_ulong)
    kernel32.Process32FirstW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.Process32NextW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel32.GetProcessTimes.argtypes = (ctypes.c_void_p,) + (ctypes.POINTER(ctypes.c_ulonglong),) * 4
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    return kernel32


def _windows_parents() -> dict[int, int]:
    import ctypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", ctypes.c_ulong),
                    ("cntThreads", ctypes.c_ulong), ("th32ParentProcessID", ctypes.c_ulong),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                    ("szExeFile", ctypes.c_wchar * 260)]

    TH32CS_SNAPPROCESS, INVALID_HANDLE_VALUE = 0x2, ctypes.c_void_p(-1).value
    kernel32 = _kernel32()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise OSError("CreateToolhelp32Snapshot failed")
    try:
        entry = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        parents = {}
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return parents
    finally:
        kernel32.CloseHandle(snapshot)


def _windows_cpu_seconds(pid: int) -> float | None:
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        # FILETIMEs in 100 ns units: creation, exit, kernel, user
        times = [ctypes.c_ulonglong() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            return None
        return (times[2].value + times[3].value) / 10_000_000
    finally:
        kernel32.CloseHandle(handle)


def _ps_seconds(clock: str) -> float:
    # [[dd-]hh:]mm:ss[.cc]
    days, _, clock = clock.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + float(days or 0) * 86_400


def _posix_table() -> dict[int, tuple[int, float]]:
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,time="], capture_output=True, text=True,
                         check=True).stdout
    table = {}
    for line in out.splitlines():
        pid, ppid, clock = line.split()
        table[int(pid)] = (int(ppid), _ps_seconds(clock))
    return table


def _descendants(root: int, parents: dict[int, int]) -> list[int]:
    found, stack = [], [root]
    while stack:
        pid = stack.pop()
        found.append(pid)
        stack += [child for child, parent in parents.items() if parent == pid and child != pid]
    return found


def tree_cpu_seconds(pid: int) -> float | None:
    """User plus kernel CPU time of `pid` and every process under it. None when
    `pid` cannot be read, which disables the idle kill rather than risking a
    working generation."""
    try:
        if _WINDOWS:
            parents = _windows_parents()
            if pid not in parents:
                return None
            root = _windows_cpu_seconds(pid)
            if root is None:
                return None
            # a child that cannot be opened counts for nothing rather than blocking the reading
            return root + sum(_windows_cpu_seconds(child) or 0.0 for child in _descendants(pid, parents)[1:])
        table = _posix_table()
        if pid not in table:
            return None
        parents = {child: parent for child, (parent, _) in table.items()}
        return sum(table[member][1] for member in _descendants(pid, parents))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def run_generate(cmd: list[str], *, cwd: str, env: dict[str, str], on_line: Callable[[str], None],
                 idle_timeout: float = IDLE_TIMEOUT, poll: float = 1.0, tail_lines: int = 20,
                 tree_cpu: Callable[[int], float | None] = tree_cpu_seconds,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> GenerateResult:
    """Run Generate to completion, feeding each stdout line to `on_line`.

    Blocking; run it on a worker thread. The process is killed once it has gone
    `idle_timeout` seconds without writing a line or using CPU time anywhere in
    its tree, the shape of a process waiting on input nobody will give it.
    """
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                    "encoding": "utf-8", "errors": "replace", "bufsize": 1, "cwd": cwd, "env": env}
    if _WINDOWS:
        # console-subsystem exe: no window flashing over the launcher
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(cmd, **kwargs)
    tail: deque[str] = deque(maxlen=tail_lines)
    stderr_lines: list[str] = []
    lines_seen = [0]

    def pump(stream, sink: Callable[[str], None]) -> None:
        for line in stream:
            sink(line.rstrip("\r\n"))
            lines_seen[0] += 1

    def on_stdout(line: str) -> None:
        tail.append(line)
        on_line(line)

    pumps = [threading.Thread(target=pump, args=(process.stdout, on_stdout), name="GenerateStdout", daemon=True),
             threading.Thread(target=pump, args=(process.stderr, stderr_lines.append), name="GenerateStderr",
                              daemon=True)]
    for thread in pumps:
        thread.start()

    result = GenerateResult(returncode=None)
    quiet_since = clock()
    last_cpu = tree_cpu(process.pid)
    seen = lines_seen[0]
    while process.poll() is None:
        sleep(poll)
        now = clock()
        cpu = tree_cpu(process.pid)
        if cpu is None or cpu != last_cpu or lines_seen[0] != seen:
            quiet_since, last_cpu, seen = now, cpu, lines_seen[0]
        elif now - quiet_since >= idle_timeout:
            process.kill()
            result.killed = True
            result.idle_seconds = now - quiet_since
            break
    result.returncode = process.wait()
    # a grandchild holding the pipes keeps a pump alive past the kill
    for thread in pumps:
        thread.join(timeout=5)
    result.stderr = "\n".join(stderr_lines)
    result.tail = list(tail)
    return result
