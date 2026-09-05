"""
Bottom-bar navigation model shared by every screen's BottomAppBar.

Kivy-free on purpose: the GUI-side unit tests load it by file path.
"""
from __future__ import annotations

__all__ = ("NavEntry", "ClientTab", "BUILTIN_NAV", "nav_entries",
           "icon_is_image", "world_component_icon")

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class NavEntry:
    name: str
    label: str
    icon: str


@dataclass
class ClientTab:
    """Handle returned by add_client_tab(); world clients store it and hand it
    back to remove_client_tab(). `text` mirrors the button handle it replaced."""
    name: str
    content: object = None
    icon: str = "puzzle-outline"

    @property
    def text(self) -> str:
        return self.name


def icon_is_image(icon: str) -> bool:
    """Image path or ap:/ap:zip: URL rather than a Material icon name."""
    return any(sep in icon for sep in ("/", "\\", ":"))


def world_component_icon(ctx_module: str, components: Iterable,
                         icon_paths: Mapping[str, str]) -> Optional[str]:
    """Icon of the launcher component the world package owning `ctx_module`
    registered ("worlds.sms.SMSClient" -> "worlds.sms"). Client components
    win over other kinds; the shared default key "icon" counts as none."""
    parts = ctx_module.split(".")
    if len(parts) < 2 or parts[0] != "worlds":
        return None
    package = ".".join(parts[:2])
    found = None
    for component in components:
        module = getattr(getattr(component, "func", None), "__module__", None) or ""
        if module != package and not module.startswith(package + "."):
            continue
        key = getattr(component, "icon", None)
        icon = icon_paths.get(key) if key and key != "icon" else None
        if not icon:
            continue
        if getattr(getattr(component, "type", None), "name", "") == "CLIENT":
            return icon
        found = found or icon
    return found


# Fixed slots, in display order. Console/Hint always show; Tracker/Map show
# once their screens exist; Admin follows the client.admin_console setting.
BUILTIN_NAV = (
    NavEntry("console", "Console", "chat-outline"),
    NavEntry("hint", "Hint", "magnifying_glass_location"),
    NavEntry("tracker", "Tracker", "list_check"),
    NavEntry("map", "Map", "map-outline"),
    NavEntry("admin", "Admin", "shield-key-outline"),
)
_ALWAYS = ("console", "hint")
_SCREEN_GATED = ("tracker", "map")


def nav_entries(screen_names: Iterable[str], client_tabs: Iterable[ClientTab],
                admin_enabled: bool) -> list[NavEntry]:
    """Ordered nav entries: the visible builtins, then client tabs that don't
    map onto a builtin slot, in registration order."""
    names = set(screen_names)
    shown = set(_ALWAYS) | (set(_SCREEN_GATED) & names)
    if admin_enabled:
        shown.add("admin")
    entries = [entry for entry in BUILTIN_NAV if entry.name in shown]
    builtin_names = {entry.name for entry in BUILTIN_NAV}
    entries.extend(NavEntry(tab.name, tab.name, tab.icon)
                   for tab in client_tabs if tab.name not in builtin_names)
    return entries
