from __future__ import annotations
"""
ADMIN SCREEN
AdminScreen - host administration: session, tag, and player info on the
left; server option fields top-right; the console minus item traffic
bottom-right, with the admin command input on the bar's FAB.

Data arrives through app.on_admin_command_result: the `players` and
`options` payloads MultiServer attaches to /players, /options and /option
replies, and the `/status <tag>` replies, parsed from their text so they
work against any server. Every !admin command is broadcast to all players
as chat, so the screen fetches once on first entry and otherwise refreshes
on demand. Opt-in via client.admin_console; app.change_screen gates it
behind AdminLoginDialog until the server confirms the host login.
"""
__all__ = ("AdminScreen", "AdminHeader", "AdminInfoPane", "AdminOptionsPane")

from collections import deque
from time import time

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from mwgg_gui.components.admin_commands import (
    STATUS_TAGS, admin_say_line, format_last_activity, format_session_time, option_entries,
    parse_status_reply, player_display_name, status_name, tagged_players)
from mwgg_gui.components.bottomappbar import BottomAppBar
from mwgg_gui.console.console import ConsoleLayout
from mwgg_gui.console.textconsole import ConsoleView
from mwgg_gui.settings.settings_components import LabeledDropdown, LabeledSwitch

Builder.load_string('''
<AdminHeader>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(36)
    padding: dp(12), 0
    MDLabel:
        text: "Host Administration"
        font_style: "Title"
        role: "medium"
        theme_text_color: "Custom"
        text_color: app.theme_cls.primaryColor
    MDLabel:
        text: root.status_text
        halign: "right"
        font_style: "Body"
        role: "medium"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceVariantColor

<AdminSection>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: 0, dp(4)
    MDBoxLayout:
        id: title_row
        orientation: "horizontal"
        size_hint_y: None
        height: dp(32)
        MDLabel:
            text: root.title
            font_style: "Title"
            role: "small"
            theme_text_color: "Custom"
            text_color: app.theme_cls.primaryColor
            pos_hint: {"center_y": 0.5}
    MDBoxLayout:
        id: body
        orientation: "vertical"
        size_hint_y: None
        height: self.minimum_height

<InfoRow>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(24)
    MDLabel:
        text: root.key
        size_hint_x: 0.4
        font_style: "Body"
        role: "small"
        theme_text_color: "Custom"
        text_color: app.theme_cls.onSurfaceVariantColor
    MDLabel:
        text: root.value
        font_style: "Body"
        role: "small"
        shorten: True
        shorten_from: "right"

<PlayerCell>:
    size_hint_y: None
    height: dp(24)
    font_style: "Body"
    role: "small"
    shorten: True
    shorten_from: "right"

<OptionFieldRow>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(56)
    spacing: dp(8)
    MDLabel:
        text: root.text
        size_hint_x: 0.5
        theme_text_color: "Secondary"
        pos_hint: {"center_y": 0.5}
''')

_PLAYER_COLUMNS = (("Name", 0.28), ("Game", 0.26), ("Status", 0.13), ("Checks", 0.12),
                   ("Last active", 0.15), ("", 0.06))
_NO_PLAYERS_HINT = "No player data yet. Refresh to fetch /players."
_STATE_TO_STATUS = {"goal": 30, "ready": 10}


def _admin_line_filter(item) -> bool:
    """Drop item sends, cheats, and hints (see ConsolePair.item_traffic);
    plain strings and log records pass."""
    return not getattr(item, "item_traffic", False)


class AdminHeader(MDBoxLayout):
    status_text = StringProperty("Not connected")

    def refresh(self, ctx) -> None:
        if not getattr(ctx, "server", None):
            self.status_text = "Not connected"
        elif getattr(ctx, "admin", False):
            self.status_text = "Logged in as host"
        else:
            self.status_text = "Not logged in"


class AdminSection(MDBoxLayout):
    """Titled block; children added after construction land in its body,
    and `on_refresh` adds a refresh button to the title row."""
    title = StringProperty("")

    def __init__(self, on_refresh=None, **kwargs):
        super().__init__(**kwargs)
        self._built = True
        if on_refresh is not None:
            button = MDIconButton(icon="refresh", pos_hint={"center_y": 0.5})
            button.bind(on_release=lambda *_: on_refresh())
            self.ids.title_row.add_widget(button)

    def add_widget(self, widget, *args, **kwargs):
        if getattr(self, "_built", False):
            return self.ids.body.add_widget(widget, *args, **kwargs)
        return super().add_widget(widget, *args, **kwargs)

    def clear_body(self) -> None:
        self.ids.body.clear_widgets()


class InfoRow(MDBoxLayout):
    key = StringProperty("")
    value = StringProperty("")


class PlayerCell(MDLabel):
    pass


class OptionFieldRow(MDBoxLayout):
    """Label + text field for int and free-form str options; Enter applies."""
    text = StringProperty("")

    def __init__(self, entry: dict, on_apply, **kwargs):
        super().__init__(**kwargs)
        self.text = entry["name"]
        value = entry.get("value")
        self.field = MDTextField(
            MDTextFieldHintText(text=entry.get("type", "str")),
            text="" if value is None else str(value))
        if entry.get("type") == "int":
            self.field.input_filter = "int"
        self.field.size_hint_x = 0.5
        self.field.pos_hint = {"center_y": 0.5}
        self.field.write_tab = False

        def submit(*_args):
            if self.field.text:
                on_apply(entry["name"], self.field.text)

        self.field.bind(on_text_validate=submit)
        self.add_widget(self.field)


class AdminInfoPane(MDScrollView):
    """Session timer, `/status <tag>` counts, and the players table (from
    /players rows, or from /status lines on servers without them)."""

    def __init__(self, on_refresh_players, on_refresh_tags, **kwargs):
        super().__init__(**kwargs)
        self.app = MDApp.get_running_app()
        self.rows: list[dict] = []
        self._rows_from_players = False
        self._activity_cells: list[PlayerCell] = []
        self._tag_counts: dict[str, int | None] = {tag: None for tag in STATUS_TAGS}

        self.session = AdminSection(title="Session")
        self.started_row = InfoRow(key="Started")
        self.elapsed_row = InfoRow(key="Elapsed")
        self.seed_row = InfoRow(key="Seed")
        self.server_row = InfoRow(key="Server")
        for row in (self.started_row, self.elapsed_row, self.seed_row, self.server_row):
            self.session.add_widget(row)

        self.tags = AdminSection(title="Tags", on_refresh=on_refresh_tags)
        self.tag_rows = {tag: InfoRow(key=tag, value="?") for tag in STATUS_TAGS}
        for row in self.tag_rows.values():
            self.tags.add_widget(row)

        self.players = AdminSection(title="Players", on_refresh=on_refresh_players)
        self.players_grid = MDGridLayout(cols=len(_PLAYER_COLUMNS), adaptive_height=True,
                                         spacing=(dp(4), 0))
        self.players.add_widget(self.players_grid)
        self.players_hint = MDLabel(text=_NO_PLAYERS_HINT, font_style="Body", role="small",
                                    adaptive_height=True, theme_text_color="Secondary")
        self.players.add_widget(self.players_hint)

        column = MDBoxLayout(orientation="vertical", adaptive_height=True,
                             padding=[dp(12), dp(4)], spacing=dp(4))
        column.add_widget(self.session)
        column.add_widget(self.tags)
        column.add_widget(self.players)
        self.add_widget(column)

    def refresh_session(self, ctx) -> None:
        now = time()
        started, elapsed = format_session_time(getattr(ctx, "timer", 0.0) or 0.0, now)
        self.started_row.value = started
        self.elapsed_row.value = elapsed
        self.seed_row.value = str(getattr(ctx, "seed_name", None)
                                  or getattr(ctx, "server_seed_name", None) or "")
        self.server_row.value = str(getattr(ctx, "server_address", None) or "")
        self._render_tag_rows(getattr(ctx, "current_energy_link_value", None))
        for row, cell in zip(self.rows, self._activity_cells):
            if "last_activity" in row:
                cell.text = format_last_activity(row.get("last_activity"), now)

    def _render_tag_rows(self, energy) -> None:
        for tag, row in self.tag_rows.items():
            count = self._tag_counts[tag]
            if count is None:
                row.value = "?"
                continue
            row.value = f"{count} player{'s' if count != 1 else ''}"
            if tag == "EnergyLink" and energy is not None:
                row.value += f", {energy} energy"

    def set_tag_status(self, tag: str, players: list[dict]) -> None:
        """Count from one `/status <tag>` reply (all teams already merged)."""
        if tag in self._tag_counts:
            self._tag_counts[tag] = tagged_players(players)
        self._render_tag_rows(getattr(self.app.ctx, "current_energy_link_value", None))

    def set_players(self, rows: list[dict]) -> None:
        """Rows from /players: the richest source, never replaced by /status."""
        self._rows_from_players = True
        self._render_players(rows)

    def set_players_from_status(self, players: list[dict]) -> None:
        """Fallback table from `/status` lines, used until /players rows arrive."""
        if self._rows_from_players:
            return
        self._render_players([{
            "name": player["name"], "connected": player["connections"] > 0,
            "checks": player["checks"], "total": player["total"],
            "status": _STATE_TO_STATUS.get(player["state"]),
        } for player in players])

    def _render_players(self, rows: list[dict]) -> None:
        self.rows = list(rows)
        self.players_grid.clear_widgets()
        self._activity_cells = []
        self.players_hint.text = "" if self.rows else _NO_PLAYERS_HINT
        for title, width in _PLAYER_COLUMNS:
            self.players_grid.add_widget(PlayerCell(text=title, bold=True, size_hint_x=width))
        now = time()
        for row in self.rows:
            status = row.get("status")
            cells = (
                player_display_name(row),
                row.get("game", ""),
                status_name(status) if status is not None else "",
                f"{row.get('checks', 0)}/{row.get('total', 0)}",
                format_last_activity(row["last_activity"], now) if "last_activity" in row else "",
            )
            for (_, width), text in zip(_PLAYER_COLUMNS, cells):
                cell = PlayerCell(text=text, size_hint_x=width)
                self.players_grid.add_widget(cell)
            self._activity_cells.append(cell)
            self.players_grid.add_widget(MDIcon(
                icon="check-circle" if row.get("connected") else "circle-outline",
                size_hint_x=_PLAYER_COLUMNS[-1][1], pos_hint={"center_y": 0.5}))
        self.refresh_session(self.app.ctx)


class AdminOptionsPane(MDScrollView):
    """One row per server option; each control applies through
    `/option <name> <value>` on its own."""

    def __init__(self, on_apply, on_refresh, **kwargs):
        super().__init__(**kwargs)
        self.on_apply = on_apply
        self.section = AdminSection(title="Server options", on_refresh=on_refresh)
        column = MDBoxLayout(orientation="vertical", adaptive_height=True,
                             padding=[dp(12), dp(4)])
        column.add_widget(self.section)
        self.add_widget(column)

    def set_entries(self, entries: list[dict]) -> None:
        self.section.clear_body()
        for entry in entries:
            name = entry["name"]
            if entry.get("type") == "bool":
                self.section.add_widget(LabeledSwitch(
                    text=name, active=bool(entry.get("value")),
                    on_switch=lambda _switch, value, name=name: self.on_apply(name, str(value))))
            elif entry.get("choices"):
                self.section.add_widget(LabeledDropdown(
                    text=name, items=list(entry["choices"]),
                    current_item=str(entry.get("value") if entry.get("value") is not None else ""),
                    on_select=lambda value, name=name: self.on_apply(name, value)))
            else:
                self.section.add_widget(OptionFieldRow(entry, self.on_apply))


class AdminScreen(MDScreen, ThemableBehavior):
    """Admin console (see module docstring). Built by app._create_screen("admin")
    once client.admin_console is on and the host login passed."""
    name = "admin"
    app: MDApp
    bottom_appbar: BottomAppBar
    console_view: ConsoleView
    header: AdminHeader
    info_pane: AdminInfoPane
    options_pane: AdminOptionsPane

    def __init__(self, **kwargs):
        self.app = MDApp.get_running_app()
        self.size_hint = (1, 1)
        self.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        super().__init__(**kwargs)
        self._status_event = None
        self._fetched = False
        # Tags of the /status requests this screen sent and has not yet seen
        # answered, for replies whose text names no tag; per-team player
        # lists from the latest replies feed the fallback players table.
        self._pending_status: deque[str] = deque()
        self._last_status_tag: str | None = None
        self._status_teams: dict[int, list[dict]] = {}
        self._tag_teams: dict[str, dict[int, list[dict]]] = {}
        self.bottom_appbar = BottomAppBar(screen_name="admin")
        self.header = AdminHeader()
        self.info_pane = AdminInfoPane(on_refresh_players=self.refresh_players,
                                       on_refresh_tags=self.refresh_tags, size_hint_x=0.38)
        self.options_pane = AdminOptionsPane(on_apply=self.apply_option,
                                             on_refresh=self.refresh_options, size_hint_y=0.45)

        # Mirror the console from now on; only one console may drain
        # app.text_buffer (see TextConsole.mirrors).
        console = getattr(getattr(self.app, "console_screen", None), "ui_console", None)
        self.console_view = ConsoleView(
            mirror_of=console.text_console if console is not None else None,
            line_filter=_admin_line_filter, size_hint=(1, 0.55))
        self.console_view.text_console.size_hint = (1, 1)

        right = MDBoxLayout(orientation="vertical", size_hint_x=0.62, spacing=dp(4))
        right.add_widget(self.options_pane)
        right.add_widget(self.console_view)
        body = MDBoxLayout(orientation="horizontal", spacing=dp(8))
        body.add_widget(self.info_pane)
        body.add_widget(right)
        column = MDBoxLayout(orientation="vertical", size_hint=(1, 1),
                             pos_hint={"x": 0, "y": 0}, padding=[dp(4), dp(4)])
        column.add_widget(self.header)
        column.add_widget(body)
        self.layout = ConsoleLayout()
        self.layout.add_widget(column)
        self.add_widget(self.layout)
        self.add_widget(self.bottom_appbar)

        snapshot = getattr(self.app, "_admin_snapshot", {}) or {}
        self.receive_admin_result(snapshot)
        if "options" not in snapshot:
            self.options_pane.set_entries(self._local_option_entries())
        self.info_pane.refresh_session(self.app.ctx)

    def _local_option_entries(self, payload=None) -> list[dict]:
        ctx = self.app.ctx
        return option_entries(payload, hint_cost=getattr(ctx, "hint_cost", None),
                              check_points=getattr(ctx, "check_points", None),
                              permissions=getattr(ctx, "permissions", None))

    def receive_admin_result(self, args: dict) -> None:
        """An admin reply (see app.on_admin_command_result): structured
        `players` / `options` payloads, or a `/status` reply parsed from
        its text (`status` names its team and tag on newer servers)."""
        if "players" in args:
            self.info_pane.set_players(args["players"])
        if "options" in args:
            self.options_pane.set_entries(self._local_option_entries(args["options"]))
        text = "".join(part.get("text", "") for part in args.get("data", []))
        parsed = parse_status_reply(text)
        if parsed is not None:
            self._receive_status(parsed, args.get("status") or {})

    def _receive_status(self, parsed: dict, payload: dict) -> None:
        team, players = parsed["team"], parsed["players"]
        # Replies come one per team, in request order; team 0 consumes the
        # pending tag when neither the payload nor the text names one.
        expected = self._pending_status.popleft() if team == 0 and self._pending_status else None
        tag = payload.get("tag") or parsed["tag"] or expected or self._last_status_tag
        self._status_teams[team] = players
        self.info_pane.set_players_from_status(
            [player for _, team_players in sorted(self._status_teams.items())
             for player in team_players])
        if not tag:
            return
        self._last_status_tag = tag
        teams = self._tag_teams.setdefault(tag, {})
        teams[team] = players
        self.info_pane.set_tag_status(
            tag, [player for team_players in teams.values() for player in team_players])

    def send_admin(self, text: str) -> None:
        self.app.on_message(admin_say_line(text), None)

    def refresh_players(self) -> None:
        self.send_admin("/players")

    def refresh_tags(self) -> None:
        for tag in STATUS_TAGS:
            self._pending_status.append(tag)
            self.send_admin(f"/status {tag}")

    def refresh_options(self) -> None:
        self.send_admin("/options")

    def apply_option(self, name: str, value: str) -> None:
        self.send_admin(f"/option {name} {value}")

    def _tick(self, dt) -> None:
        self.header.refresh(self.app.ctx)
        self.info_pane.refresh_session(self.app.ctx)

    def on_pre_enter(self, *args):
        self._tick(0)
        if self._status_event is None:
            self._status_event = Clock.schedule_interval(self._tick, 1)
        if not self._fetched and getattr(self.app.ctx, "admin", False):
            # Each fetch is broadcast as chat, so only the first entry pulls
            # everything; the section buttons refresh on demand.
            self._fetched = True
            self.refresh_players()
            self.refresh_tags()
            self.refresh_options()

    def on_leave(self, *args):
        if self._status_event is not None:
            self._status_event.cancel()
            self._status_event = None
        # A detached screen gets no HoverBehavior on_leave, so drop a tooltip left on Window.
        self.console_view.text_console.remove_tooltip()
