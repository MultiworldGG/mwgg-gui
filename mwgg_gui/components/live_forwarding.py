"""Attribute forwarding between the live launcher app and its stand-ins."""
from __future__ import annotations

__all__ = ("LiveForwarding",)


class LiveForwarding:
    """Resolve names this instance lacks from the live launcher instance,
    then from the legacy kvui manager registered on it.

    Both targets forward their own missing names back to the running app,
    so a name already being resolved on this instance raises at once
    instead of bouncing between the two ``__getattr__`` methods until
    RecursionError; ``getattr(ui, name, default)`` then returns default.
    """

    _active_instance = None

    def __getattr__(self, name: str):
        state = self.__dict__
        pending = state.setdefault("_forwarding_names", set())
        if name in pending:
            raise AttributeError(name)
        pending.add(name)
        try:
            live = type(self)._active_instance
            if live is not None and live is not self:
                try:
                    return getattr(live, name)
                except AttributeError:
                    pass
            manager = state.get("_legacy_kvui_manager")
            if manager is not None and manager is not self:
                try:
                    return getattr(manager, name)
                except AttributeError:
                    pass
            raise AttributeError(name)
        finally:
            pending.discard(name)
