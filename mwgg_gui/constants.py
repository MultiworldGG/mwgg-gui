from __future__ import annotations
"""
Dictionary of constants for the MultiWorld GUI application

Contains the actions for the console and launcher.
"""

__all__ = (
    "CONSOLE_ACTIONS",
    "LAUNCHER_ACTIONS",
    "MWGG_WEBHOST_BASE",
    "TRUSTED_AVATAR_HOSTS",
    "AVATAR_TOKEN_MINT_URL",
    "AVATAR_UPLOAD_URL",
    "AVATAR_FILE_EXTENSIONS",
)

# Host that mints upload tokens and serves uploaded avatars. Will move to
# https://multiworld.gg once the uploader is rolled out there.
MWGG_WEBHOST_BASE = "https://prismativerse.com"

# Hosts whose avatar URLs the client is willing to render. URLs that fail this
# check (legacy YAML entries, manually-edited persistent storage, or hostile
# Set values from other clients) collapse to the default avatar.
TRUSTED_AVATAR_HOSTS = ("multiworld.gg", "prismativerse.com")

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
}]


LAUNCHER_ACTIONS = [
{
    "id":           "connect",
    "buttonicon":   "lan-connect",
    "icon":         "lan-connect",
    "prefill":      "",
    "label":        "Connect",
    "indicator":    "blank",
    "type":         "assist",
},
]
