"""Attribute forwarding between the live launcher app and its stand-ins."""
from __future__ import annotations

import functools

__all__ = ("LiveForwarding", "prefer_manager_override")


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


def prefer_manager_override(*adopt: str):
    """Decorate a live-app kvui hook so the registered legacy manager's own
    override of it runs instead, as it would upstream.

    A manager method that re-enters the hook (``super()`` on a make_gui()
    subclass, or a stub forwarding to the running app) gets the default body.
    ``adopt`` names attributes the override assigns on the stand-in that the
    live app's hooks read back, such as an upstream ``enable_energy_link``'s
    ``self.energy_link_label``.
    """
    def decorate(method):
        name = method.__name__

        @functools.wraps(method)
        def hook(self, *args, **kwargs):
            live = type(self)._active_instance
            if live is None:
                live = self
            state = live.__dict__
            pending = state.setdefault("_overriding_hooks", set())
            manager = state.get("_legacy_kvui_manager")
            impl = getattr(type(manager), name, None)
            if impl is None or impl is getattr(type(live), name, None) or name in pending:
                return method(self, *args, **kwargs)
            pending.add(name)
            try:
                result = getattr(manager, name)(*args, **kwargs)
            finally:
                pending.discard(name)
            assigned = vars(manager)
            for attr in adopt:
                if attr in assigned:
                    setattr(live, attr, assigned[attr])
            return result
        return hook
    return decorate
