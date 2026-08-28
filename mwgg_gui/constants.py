from __future__ import annotations
"""
Constants for the MultiworldGG GUI application

Contains the actions for the console and launcher.
"""

__all__ = (
    "ROLE_LAUNCHER",
    "ROLE_CLIENT",
    "CONSOLE_ACTIONS",
    "LAUNCHER_ACTIONS",
    "MWGG_WEBHOST_BASE",
    "TRUSTED_AVATAR_HOSTS",
    "AVATAR_TOKEN_MINT_URL",
    "AVATAR_UPLOAD_URL",
    "AVATAR_FILE_EXTENSIONS",
)

# Process roles from the MWGG_ROLE env var (set by MultiWorld.py/Launcher.py):
# "launcher" spawns clients as separate processes; "client" boots straight to
# one game's console.
ROLE_LAUNCHER = "launcher"
ROLE_CLIENT = "client"

# Host that mints upload tokens and serves uploaded avatars. Will move to
# https://multiworld.gg once the uploader is rolled out there.
MWGG_WEBHOST_BASE = "https://mw.prismativerse.com"

# Avatar URLs failing this host check (legacy YAML entries, hand-edited
# storage, hostile Set values) collapse to the default avatar.
TRUSTED_AVATAR_HOSTS = ("multiworld.gg", "mw.prismativerse.com")

AVATAR_TOKEN_MINT_URL = f"{MWGG_WEBHOST_BASE}/api/avatar/token"
AVATAR_UPLOAD_URL = f"{MWGG_WEBHOST_BASE}/api/avatar/upload"

AVATAR_FILE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

CONSOLE_ACTIONS = [
{
    "id":           "console",
    "buttonicon":   "chat-outline",
    "icon":         "chat-outline",
    "prefill":      "!countdown",
    "label":        "Console",
    "indicator":    "blank",
    "type":         "assist",
},
{
    "id":           "hint",
    "buttonicon":   "map-search",
    "icon":         "map-search",
    "prefill":      "!hint",
    "label":        "Hint",
    "indicator":    "widgets",
    "type":         "assist",
},
{
    "id":           "admin",
    "buttonicon":   "account-lock-outline",
    "icon":         "wrench",
    "prefill":      "password",
    "label":        "Host Administration",
    "indicator":    "server-network",
    "type":         "assist",
},
{
    # Client-direct reconnect (see components/connect_dialog.py); special-cased
    # in BottomAppBar.on_bar_action to open the dialog instead of animating the
    # text input.
    "id":           "connect",
    "buttonicon":   "lan-connect",
    "icon":         "lan-connect",
    "prefill":      "",
    "label":        "Connect",
    "indicator":    "blank",
    "type":         "assist",
}]


LAUNCHER_ACTIONS = [
{
    # Special-cased in BottomAppBar.on_bar_action to call the launcher screen's
    # connect() directly -- no live connection for the command processor.
    "id":           "launch",
    "buttonicon":   "rocket-launch",
    "icon":         "rocket-launch",
    "prefill":      "",
    "label":        "Launch",
    "indicator":    "blank",
    "type":         "assist",
},
]
