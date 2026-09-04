from __future__ import annotations
"""
Constants for the MultiworldGG GUI application

Contains the bottom-bar text-input actions.
"""

__all__ = (
    "ROLE_LAUNCHER",
    "ROLE_CLIENT",
    "TEXT_INPUT_ACTIONS",
    "MWGG_WEBHOST_BASE",
    "SETUP_GUIDE_URL",
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

# Webhost setup-guide route, /learn/<lang>/tutorial/<game>/<file>. A world's
# declared guide file names are readable only by importing the world, so the
# English `setup` guide is the only one the GUI can name.
SETUP_GUIDE_URL = f"{MWGG_WEBHOST_BASE}/learn/en/tutorial/{{game}}/setup"

# Avatar URLs failing this host check (legacy YAML entries, hand-edited
# storage, hostile Set values) collapse to the default avatar.
TRUSTED_AVATAR_HOSTS = ("multiworld.gg", "mw.prismativerse.com")

AVATAR_TOKEN_MINT_URL = f"{MWGG_WEBHOST_BASE}/api/avatar/token"
AVATAR_UPLOAD_URL = f"{MWGG_WEBHOST_BASE}/api/avatar/upload"

AVATAR_FILE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Text inputs the bottom bar's FAB slides up, keyed by screen name; the key
# doubles as BottomBarTextInput.action_type.
TEXT_INPUT_ACTIONS = {
    "console": {"icon": "chat-outline", "label": "Console"},
    "hint": {"icon": "map-search", "label": "Hint"},
    "admin": {"icon": "wrench", "label": "Host Administration"},
}
