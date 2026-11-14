"""A world's legacy kvui manager, built against the live app after the takeover."""
from __future__ import annotations

import logging

__all__ = ("build_legacy_manager", "take_over_live_app")

logger = logging.getLogger("Client")


def build_legacy_manager(live, ctx, manager):
    """Build a world's manager against the live app as kivy's App.run would:
    build(), then on_start.

    kvui.GameManager subclasses build themselves (``build_for_live_app``);
    any other manager subclasses the live app's class and builds as a
    phantom instance.

    Args:
        live: The running frontend app.
        ctx: The game context that took over the live app.
        manager: The world's manager class from make_gui(), or the instance
            its own run_gui made.
    """
    made = not isinstance(manager, type)
    manager_cls = type(manager) if made else manager
    build_for_live_app = getattr(manager_cls, "build_for_live_app", None)
    if build_for_live_app is not None:
        if made:
            return build_for_live_app(ctx, live, manager=manager)
        return build_for_live_app(ctx, live)

    if not made:
        manager = manager_cls(ctx)
    manager._attach_legacy_surface(live)
    root = manager.build()
    if root:
        manager.root = root
    live._legacy_kvui_manager = manager
    # The subclass declares the window title (class attr or a build()
    # write); the live app owns the property.
    default = (manager.property("base_title").defaultvalue
               if isinstance(manager, type(live)) else "")
    title = getattr(manager, "base_title", default)
    if isinstance(title, str) and title and title != default:
        live.base_title = title
    # the live app's own on_start ran long before
    try:
        manager.dispatch("on_start")
    except Exception:
        logger.exception("Legacy client on_start failed")
    return manager


async def take_over_live_app(ctx) -> None:
    """kvui.GameManager.async_run for a phantom a world's run_gui started
    as a standalone app."""
    if ctx._can_takeover_existing_ui():
        await ctx._takeover_existing_ui()
        return
    logger.critical("Client did not launch properly, exiting.")
    error_callback = getattr(ctx, "_error_callback", None)
    if error_callback is not None:
        error_callback()
