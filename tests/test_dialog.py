"""MessageBox text guard (components/dialog.py).

dialog.py imports Kivy and KivyMD at module level, so it is loaded by file
path with those imports stubbed; the text guard under test is pure Python.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

_PATH = Path(__file__).resolve().parent.parent / "mwgg_gui" / "components" / "dialog.py"


class _Stub:
    def __init__(self, *args, **kwargs):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture(scope="module")
def dialog():
    stubs = {
        "kivy": _stub("kivy"),
        "kivy.metrics": _stub("kivy.metrics", dp=lambda value: value),
        "kivy.properties": _stub("kivy.properties", ObjectProperty=_Stub),
        "kivy.uix": _stub("kivy.uix"),
        "kivy.uix.widget": _stub("kivy.uix.widget", Widget=_Stub),
        "kivymd": _stub("kivymd"),
        "kivymd.app": _stub("kivymd.app", MDApp=types.SimpleNamespace(get_running_app=lambda: None)),
        "kivymd.uix": _stub("kivymd.uix"),
        "kivymd.uix.boxlayout": _stub("kivymd.uix.boxlayout", MDBoxLayout=_Stub),
        "kivymd.uix.button": _stub("kivymd.uix.button", MDButton=_Stub, MDButtonText=_Stub),
        "kivymd.uix.dialog": _stub(
            "kivymd.uix.dialog", MDDialog=_Stub, MDDialogHeadlineText=_Stub, MDDialogSupportingText=_Stub,
            MDDialogButtonContainer=_Stub, MDDialogContentContainer=_Stub),
        "kivymd.uix.label": _stub("kivymd.uix.label", MDLabel=_Stub),
        "kivymd.uix.scrollview": _stub("kivymd.uix.scrollview", MDScrollView=_Stub),
        "kivymd.uix.selectioncontrol": _stub("kivymd.uix.selectioncontrol", MDCheckbox=_Stub),
        "kivymd.uix.textfield": _stub("kivymd.uix.textfield", MDTextField=_Stub, MDTextFieldHelperText=_Stub),
    }
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("dialog_under_test", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def test_a_traceback_keeps_only_its_exception_lines(dialog):
    message = (
        "Patch failed with code 1:\n"
        "Traceback (most recent call last):\n"
        '  File "Patch.py", line 3, in <module>\n'
        "    main()\n"
        "    ~~~~^^\n"
        "KeyError: 'rom'\n"
        "\n"
        "During handling of the above exception, another exception occurred:\n"
        "\n"
        "Traceback (most recent call last):\n"
        '  File "Patch.py", line 5, in <module>\n'
        "    raise ValueError('no rom')\n"
        "ValueError: no rom\n"
        " Which caused: KeyError: 'rom'"
    )
    assert dialog.dialog_text(message) == (
        "Patch failed with code 1:\nKeyError: 'rom'\n\nValueError: no rom\n Which caused: KeyError: 'rom'")


def test_a_long_message_is_capped(dialog):
    many_lines = dialog.dialog_text("\n".join(f"log line {index}" for index in range(200)))
    assert many_lines.splitlines() == [f"log line {index}" for index in range(dialog.MAX_MESSAGE_LINES)] + ["..."]
    one_line = dialog.dialog_text("x" * 50_000)
    assert len(one_line) <= dialog.MAX_MESSAGE_CHARS + len("...")
    assert one_line.endswith("...")


def test_a_short_message_is_unchanged(dialog):
    message = "The Game client could not be started.\n\nDetails are in the logs folder."
    assert dialog.dialog_text(message) == message


def test_message_box_guards_its_text(dialog):
    box = dialog.MessageBox("Generation Failed", "Traceback (most recent call last):\n  File \"x\"\nKeyError: 'x'")
    assert box.message == "KeyError: 'x'"
