"""
Admin command-line helpers for the bottom bar's admin input.

Kivy-free on purpose: the GUI-side unit tests load it by file path.
"""
from __future__ import annotations

__all__ = ("ADMIN_COMMANDS", "available_admin_commands", "admin_say_line",
           "complete_admin_command", "OPTION_SPECS", "STATUS_TAGS", "option_entries",
           "parse_status_reply", "tagged_players", "player_display_name", "player_state",
           "state_icon", "enrich_player_rows", "format_session_time")

import re
from datetime import datetime
from os.path import commonprefix
from time import gmtime, strftime

# (command, usage). Server commands mirror MultiServer.ServerCommandProcessor;
# login/logout are the !admin session commands.
ADMIN_COMMANDS = (
    ("login", "login <password>"),
    ("logout", "logout"),
    ("help", "help"),
    ("players", "players"),
    ("status", "status [tag]"),
    ("save", "save"),
    ("exit", "exit"),
    ("alias", "alias <player_name> <alias>"),
    ("collect", "collect <player_name>"),
    ("countdown", "countdown [seconds]"),
    ("release", "release <player_name>"),
    ("goal", "goal <player_name>"),
    ("allow_release", "allow_release <player_name>"),
    ("forbid_release", "forbid_release <player_name>"),
    ("send", "send <player_name> <item_name>"),
    ("send_multiple", "send_multiple <amount> <player_name> <item_name>"),
    ("send_location", "send_location <player_name> <location_name>"),
    ("hint", "hint <player_name> <item_name>"),
    ("hint_multiple", "hint_multiple <amount> <player_name> <item_name>"),
    ("hint_location", "hint_location <player_name> <location_name>"),
    ("hint_location_multiple", "hint_location_multiple <amount> <player_name> <location_name>"),
    ("option", "option <option_name> <option_value>"),
    ("datastore", "datastore"),
)
_SESSION_COMMANDS = ("login", "logout")


def available_admin_commands(logged_in: bool) -> list[tuple[str, str]]:
    """Only "login" applies before authenticating, never after."""
    return [entry for entry in ADMIN_COMMANDS if (entry[0] == "login") != logged_in]


def admin_say_line(text: str) -> str:
    """The Say line the server expects for what the user typed:
    `!admin login <pw>` / `!admin logout` / `!admin /<command>`. A leading
    "/" or "!admin " is absorbed so CLI habits never produce `!admin //cmd`."""
    command = text.strip()
    if command.lower().startswith("!admin"):
        command = command[len("!admin"):].strip()
    command = command.lstrip("/").strip()
    if not command:
        return "!admin"
    if command.split(maxsplit=1)[0].lower() in _SESSION_COMMANDS:
        return f"!admin {command}"
    return f"!admin /{command}"


def complete_admin_command(text: str, logged_in: bool) -> str | None:
    """Tab completion for the bare command word: a unique match completes
    with a trailing space, several matches extend to their common prefix.
    None when there is nothing to add (no match, or arguments already
    follow). A leading "/" is preserved."""
    stripped = text.lstrip()
    prefix = "/" if stripped.startswith("/") else ""
    word = stripped[len(prefix):]
    if " " in word:
        return None
    lowered = word.lower()
    matches = [command for command, _ in available_admin_commands(logged_in)
               if command.startswith(lowered)]
    if not matches:
        return None
    if len(matches) == 1:
        return f"{prefix}{matches[0]} "
    common = commonprefix(matches)
    if len(common) <= len(word):
        return None
    return prefix + common


# The MultiServer simple_options the Admin screen edits, in display order
# (hint_mode sits with the other !command permission modes), with the
# client-side field type. The /options payload overrides these at runtime.
OPTION_SPECS = (
    ("hint_cost", "int"),
    ("location_check_points", "int"),
    ("release_mode", "str"),
    ("remaining_mode", "str"),
    ("collect_mode", "str"),
    ("hint_mode", "str"),
    ("release_threshold", "int"),
    ("item_cheat", "bool"),
    ("compatibility", "int"),
)
# Server options the pane never shows: countdown_mode only matters at room
# start, and the passwords are not edited from here.
_HIDDEN_OPTIONS = ("countdown_mode", "admin_password", "password")
# Mirrors MultiServer.Context.option_choices (what /option accepts); the
# server's /options payload carries the live list.
_FALLBACK_CHOICES = {
    "release_mode": ("goal", "enabled", "disabled", "auto", "auto_enabled"),
    "collect_mode": ("goal", "enabled", "disabled", "auto", "auto_enabled"),
    "remaining_mode": ("goal", "enabled", "disabled"),
    "countdown_mode": ("enabled", "disabled", "auto"),
    "hint_mode": ("default", "own", "all"),
}
# RoomInfo permission key -> option name.
_PERMISSION_OPTIONS = (("release", "release_mode"), ("collect", "collect_mode"),
                       ("remaining", "remaining_mode"))

# Tags the Admin screen polls with `/status <tag>`.
STATUS_TAGS = ("DeathLink", "EnergyLink", "TrapLink", "in_bk")

# MultiServer.get_status_string: one reply per team, one line per slot.
_STATUS_HEADER = re.compile(r"^Player Status on team (?P<team>\d+):")
_STATUS_LINE = re.compile(
    r"^(?P<name>.+?) has (?P<connections>\d+) connections?"
    r"(?: (?P<tagged>\d+) of which are tagged (?P<tag>\S+))?"
    r"(?: and (?P<state>has finished|is ready))?\. \((?P<checks>\d+)/(?P<total>\d+)\)$")
_STATUS_STATES = {"has finished": "goal", "is ready": "ready"}

# NetUtils.ClientStatus values that map to a distinct player state.
_GOAL_STATUS = 30
_READY_STATUS = 10
_STATE_ICONS = {"goal": "flag-checkered", "ready": "account-check",
                "connected": "check-circle", "disconnected": "lan-disconnect"}


def option_entries(payload=None, *, hint_cost=None, check_points=None,
                   permissions=None) -> list[dict]:
    """One dict per shown server option, in OPTION_SPECS order: name, type,
    value, choices (None when free-form). Starts from what RoomInfo told the
    client; the /options payload (a list of such dicts) overrides field by
    field, hidden options are dropped, and options only the server knows are
    appended."""
    by_name = {entry["name"]: entry for entry in (payload or [])
               if entry["name"] not in _HIDDEN_OPTIONS}
    local = {"hint_cost": hint_cost, "location_check_points": check_points}
    for permission, name in _PERMISSION_OPTIONS:
        if permissions and permission in permissions:
            local[name] = permissions[permission]
    entries = []
    for name, type_ in OPTION_SPECS:
        entry = {"name": name, "type": type_, "value": local.get(name),
                 "choices": _FALLBACK_CHOICES.get(name)}
        entry.update(by_name.pop(name, {}))
        entries.append(entry)
    for entry in by_name.values():
        entries.append({"choices": None, **entry})
    return entries


def parse_status_reply(text: str):
    """Parse a `/status [tag]` reply into {"team", "tag", "players"}, or None
    when the text is not one. Each player carries name, connections, tagged,
    checks, total and state ("goal", "ready" or None). `tag` is None when no
    line carried the tagged clause: the server omits it while nobody on the
    team is connected."""
    lines = text.strip().splitlines()
    header = _STATUS_HEADER.match(lines[0]) if lines else None
    if header is None:
        return None
    players, tag = [], None
    for line in lines[1:]:
        match = _STATUS_LINE.match(line.strip())
        if match is None:
            continue
        if match["tag"]:
            tag = match["tag"]
        players.append({"name": match["name"], "connections": int(match["connections"]),
                        "tagged": int(match["tagged"] or 0), "checks": int(match["checks"]),
                        "total": int(match["total"]), "state": _STATUS_STATES.get(match["state"])})
    return {"team": int(header["team"]), "tag": tag, "players": players}


def tagged_players(players) -> int:
    return sum(1 for player in players if player.get("tagged"))


def player_display_name(row: dict) -> str:
    name = row.get("name", "")
    alias = row.get("alias") or name
    return name if alias == name else f"{alias} ({name})"


def player_state(row: dict) -> str:
    """One of "goal", "ready", "connected", "disconnected": goal beats
    ready beats the connection flag, matching both /players status ints
    (NetUtils.ClientStatus) and the /status fallback's mapped status."""
    status = row.get("status")
    if status == _GOAL_STATUS:
        return "goal"
    if status == _READY_STATUS:
        return "ready"
    return "connected" if row.get("connected") else "disconnected"


def state_icon(state: str) -> str:
    return _STATE_ICONS.get(state, "help-circle-outline")


def enrich_player_rows(rows, slot_info, player_names) -> list[dict]:
    """Fill in "game" for rows the server didn't send it for, from the
    client's own connection state: by "slot" when the row carries one (the
    /players payload), else by matching the row's name against
    player_names, whose values are formatted the same way as the /status
    fallback's names (both come from MultiServer.get_aliased_name)."""
    name_to_slot = {name: slot for slot, name in player_names.items()}
    enriched = []
    for row in rows:
        if row.get("game"):
            enriched.append(row)
            continue
        slot = row.get("slot")
        if slot is None:
            slot = name_to_slot.get(row.get("name"))
        game = slot_info[slot].game if slot in slot_info else ""
        enriched.append({**row, "game": game})
    return enriched


def format_session_time(start: float, now: float) -> tuple[str, str]:
    """(local start datetime, elapsed) for the session timer; start <= 0
    means the timer never started."""
    if not start or start <= 0:
        return "Not started", "00:00:00"
    elapsed = max(0, int(now - start))
    days, remainder = divmod(elapsed, 86400)
    clock = strftime("%H:%M:%S", gmtime(remainder))
    if days:
        clock = f"{days} day{'s' if days != 1 else ''}, {clock}"
    return datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M"), clock
