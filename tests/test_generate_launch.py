"""Generate launch helpers (components/generate_launch.py); Kivy-free, loaded by file path."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "generate_launch.py"
_SPIN = "import time\nend = time.time() + {seconds}\nwhile time.time() < end: pass"


@pytest.fixture(scope="module")
def generate_launch():
    spec = importlib.util.spec_from_file_location("generate_launch_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _run(generate_launch, code: str, **kwargs):
    lines = []
    result = generate_launch.run_generate(
        [sys.executable, "-c", code], cwd=os.getcwd(), env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        on_line=lines.append, poll=0.1, **kwargs)
    return result, lines


def test_generate_env_skips_the_updater_and_kivy_args_from_source(generate_launch):
    assert generate_launch.generate_env(frozen=True) == {"PYTHONIOENCODING": "utf-8",
                                                          "SKIP_REQUIREMENTS_UPDATE": "1"}
    assert generate_launch.generate_env(frozen=False)["KIVY_NO_ARGS"] == "1"


def test_stdout_lines_reach_on_line_and_the_tail(generate_launch):
    result, lines = _run(generate_launch, "print('one'); print('two')")
    assert (result.returncode, result.killed) == (0, False)
    assert lines == ["one", "two"]
    assert result.tail == ["one", "two"]


def test_a_prompt_gets_eof_instead_of_a_hidden_console(generate_launch):
    result, _ = _run(generate_launch, "input('Press enter to close.')", idle_timeout=30)
    assert (result.returncode, result.killed) == (1, False)
    assert "EOFError" in result.stderr


def test_a_long_traceback_on_stderr_cannot_deadlock(generate_launch):
    result, lines = _run(generate_launch, "import sys; sys.stderr.write('x' * 400_000); print('done')",
                         idle_timeout=30)
    assert (result.returncode, lines) == (0, ["done"])
    assert len(result.stderr) == 400_000


def test_a_blocked_process_is_killed(generate_launch):
    result, _ = _run(generate_launch, "import time; time.sleep(60)", idle_timeout=1.0)
    assert result.killed
    assert result.returncode != 0
    assert result.idle_seconds >= 1.0
    assert "stopped responding" in result.error_message()


def test_a_working_process_is_not_killed(generate_launch):
    result, _ = _run(generate_launch, _SPIN.format(seconds=2.5), idle_timeout=1.0)
    assert (result.returncode, result.killed) == (0, False)


def test_tree_cpu_counts_a_working_child_of_an_idle_parent(generate_launch):
    # the venv's python.exe on Windows and a uv install both do their work in a child
    before = generate_launch.tree_cpu_seconds(os.getpid())
    assert before is not None
    child = subprocess.run([sys.executable, "-c", _SPIN.format(seconds=1.0)], check=False)
    assert child.returncode == 0
    assert generate_launch.tree_cpu_seconds(os.getpid()) - before < 0.5, "the finished child no longer counts"
    with subprocess.Popen([sys.executable, "-c", _SPIN.format(seconds=1.5)]) as child:
        time.sleep(1.0)
        during = generate_launch.tree_cpu_seconds(os.getpid())
    assert during - before >= 0.4
    assert generate_launch.tree_cpu_seconds(2 ** 22 + 12345) is None


def test_error_message_prefers_stderr_then_the_tail(generate_launch):
    result = generate_launch.GenerateResult(returncode=1, stderr="boom\n", tail=["ignored"])
    assert result.error_message() == "Generation failed with code 1:\nboom"
    result = generate_launch.GenerateResult(returncode=1, tail=["Generation failed: FillError: No more spots"])
    assert result.error_message().endswith("Generation failed: FillError: No more spots")
    assert generate_launch.GenerateResult(returncode=2).error_message().endswith("Unknown error")
