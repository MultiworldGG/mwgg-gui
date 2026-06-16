"""
Headless test for the callback-style MessageBox path.

Reproduces the two bugs that broke it:
  1. cancel_button was a 1-tuple (trailing comma) -> not a widget, blew up in open().
  2. callers passed error=True, but __init__ only accepts is_error.

Runs a real (hidden) MDApp so MDApp.get_running_app()/theme_cls are live, opens
the dialog, then dispatches the actual button on_release events to confirm the
callback fires with True (OK) and False (Cancel).

Run: .venv-test/Scripts/python.exe tests/test_messagebox.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# Use a throwaway KIVY_HOME so the user's customized global config (Inter font
# by relative path, inspector module) doesn't leak in and break a clean headless run.
os.environ.setdefault("KIVY_HOME", tempfile.mkdtemp(prefix="kivy_home_"))
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")

import importlib.util

from kivy.config import Config

# Drop the Windows pen/touch input providers: unused here and they crash on
# teardown (restoring a NULL window proc). Must happen before the window opens.
for _provider in ("wm_pen", "wm_touch"):
    Config.remove_option("input", _provider)

from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.button import MDButton

# Load dialog.py directly: importing the mwgg_gui package runs its __init__,
# which pulls in MultiworldGG runtime-only modules (ui_dataclasses) not on the
# path here. dialog.py has no internal imports, so it loads standalone.
_DIALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "mwgg_gui", "components", "dialog.py"
)
_spec = importlib.util.spec_from_file_location("mwgg_dialog_under_test", _DIALOG_PATH)
_dialog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dialog)
MessageBox = _dialog.MessageBox

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def find_button(dialog, label: str) -> MDButton | None:
    """Locate the MDButton whose MDButtonText reads `label`."""
    for node in dialog.walk(restrict=True):
        if isinstance(node, MDButton):
            for child in node.walk(restrict=True):
                if getattr(child, "text", None) == label:
                    return node
    return None


def run_checks(_dt) -> None:
    try:
        # --- OK path -----------------------------------------------------
        fired: list[bool] = []
        box = MessageBox(
            "Restart Required",
            "You will need to restart the launcher to apply updates.",
            is_error=True,
            callback=fired.append,
        )
        check("cancel_button is a real MDButton (not a tuple)",
              isinstance(box.cancel_button, MDButton),
              f"got {type(box.cancel_button).__name__}")

        box.open()  # would raise if cancel_button were a tuple
        check("open() built inner dialog", box.dialog is not None)

        ok_btn = find_button(box.dialog, "OK")
        check("OK button present in dialog", ok_btn is not None)
        ok_btn.dispatch("on_release")
        check("OK fires callback(True)", fired == [True], f"fired={fired}")
        check("OK clears dialog handle", box.dialog is None)

        # --- Cancel path -------------------------------------------------
        fired2: list[bool] = []
        box2 = MessageBox("Confirm", "Continue?", callback=fired2.append)
        box2.open()
        # cancel_button is the very widget that used to be a tuple
        box2.cancel_button.dispatch("on_release")
        check("Cancel fires callback(False)", fired2 == [False], f"fired={fired2}")
        check("Cancel clears dialog handle", box2.dialog is None)

        # --- error= kwarg is rejected (the launcher TypeError) -----------
        try:
            MessageBox("t", "m", error=True)  # type: ignore[call-arg]
            check("error= kwarg rejected", False, "no TypeError raised")
        except TypeError:
            check("error= kwarg rejected", True)
    except Exception as exc:  # noqa: BLE001 - surface any failure as a result
        check("no unexpected exception", False, repr(exc))
    finally:
        MDApp.get_running_app().stop()


class _TestApp(MDApp):
    def on_start(self):
        Clock.schedule_once(run_checks, 0)


def main() -> int:
    _TestApp().run()
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" -- {detail}"
        print(line)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} checks passed")
    return 1 if failed or not results else 0


if __name__ == "__main__":
    sys.exit(main())
