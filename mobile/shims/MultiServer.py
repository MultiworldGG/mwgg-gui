"""Mobile shim for the monorepo's MultiServer module.

CommonClient does `from MultiServer import CommandProcessor, mark_raw` at
import time, but the real MultiServer is the multiworld *server* — it drags
in sqlalchemy and a large server runtime that has no business inside an
APK/IPA (server hosting is explicitly out of the mobile scope).

This shim provides only the command-parsing surface the client needs:
CommandMeta, mark_raw, and CommandProcessor — copied verbatim from
MultiServer.py (keep in sync if the upstream parser changes; it has been
stable for years).
"""
import functools
import inspect
import shlex
import typing

import Utils
from Utils import async_start


class CommandMeta(type):
    def __new__(cls, name, bases, attrs):
        commands = attrs["commands"] = {}
        for base in bases:
            commands.update(base.commands)
        commands.update({command_name[5:]: method for command_name, method in attrs.items() if
                         command_name.startswith("_cmd_")})
        for command_name, method in commands.items():
            # wrap async def functions so they run on default asyncio loop
            if inspect.iscoroutinefunction(method):
                def _wrapper(self, *args, _method=method, **kwargs):
                    return async_start(_method(self, *args, **kwargs))
                functools.update_wrapper(_wrapper, method)
                commands[command_name] = _wrapper
        return super(CommandMeta, cls).__new__(cls, name, bases, attrs)


_Return = typing.TypeVar("_Return")


def mark_raw(function: typing.Callable[[typing.Any], _Return]) -> typing.Callable[[typing.Any], _Return]:
    function.raw_text = True
    return function


class CommandProcessor(metaclass=CommandMeta):
    commands: typing.Dict[str, typing.Callable]
    client = None
    marker = "/"

    def output(self, text: str):
        print(text)

    def __call__(self, raw: str) -> typing.Optional[bool]:
        if not raw:
            return
        try:
            try:
                command = shlex.split(raw, comments=False)
            except ValueError:  # most likely: "ValueError: No closing quotation"
                command = raw.split()
            basecommand = command[0]
            if basecommand[0] == self.marker:
                method = self.commands.get(basecommand[1:].lower(), None)
                if not method:
                    self._error_unknown_command(basecommand[1:])
                else:
                    if getattr(method, "raw_text", False):  # method is requesting unprocessed text data
                        arg = raw.split(maxsplit=1)
                        if len(arg) > 1:
                            return method(self, arg[1])  # argument text was found, so pass it along
                        else:
                            return method(self)  # argument may be optional, try running without args
                    else:
                        return method(self, *command[1:])  # pass each word as argument
            else:
                self.default(raw)
        except Exception as e:
            self._error_parsing_command(e)

    def get_help_text(self) -> str:
        s = ""
        for command, method in self.commands.items():
            spec = inspect.signature(method).parameters
            argtext = ""
            for argname, parameter in spec.items():
                if argname == "self":
                    continue

                if isinstance(parameter.default, str):
                    if not parameter.default:
                        argname = f"[{argname}]"
                    else:
                        argname += "=" + parameter.default
                argtext += argname
                argtext += " "
            method_doc = inspect.getdoc(method)
            if method_doc is None:
                method_doc = "(missing help text)"
            doctext = "\n    ".join(method_doc.split("\n"))
            s += f"{self.marker}{command} {argtext}\n    {doctext}\n"
        return s

    def _cmd_help(self):
        """Returns the help listing"""
        self.output(self.get_help_text())

    def _cmd_license(self):
        """Returns the licensing information"""
        license = getattr(CommandProcessor, "license", None)
        if not license:
            with open(Utils.local_path("LICENSE")) as f:
                CommandProcessor.license = f.read()
        self.output(CommandProcessor.license)

    def default(self, raw: str):
        self.output("Echo: " + raw)

    def _error_unknown_command(self, raw: str):
        self.output(f"Could not find command {raw}. Known commands: {', '.join(self.commands)}")

    def _error_parsing_command(self, exception: Exception):
        import traceback
        self.output(traceback.format_exc())
