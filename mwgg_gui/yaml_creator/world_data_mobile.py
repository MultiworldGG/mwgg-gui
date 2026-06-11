"""In-process world option introspection for mobile.

Desktop keeps world imports out of the GUI interpreter by spawning
`Generate --yaml-options` (see world_data.py). There are no subprocesses on
Android/iOS, so the mobile shell accepts the tradeoff dump_yaml_options was
designed to avoid and loads the world in-process, then reuses Generate's own
describe helpers to produce the byte-identical payload shape:

    {ok, game_name, world: {item/location names+groups}, groups: {...}}

Worlds arrive via the ModuleUpdate shim (wheel download into the sandbox
site-packages); loading after install works in the same process because
WorldSource.load() imports the module directly — the desktop EXIT_NEEDS_RELOAD
dance exists only for the freshly-`import worlds`-ed Generate subprocess.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("Client")

__all__ = ("load_world_data_in_process",)


def _ensure_world_loaded(game_name: str, module: str) -> None:
    """Install (if needed) and import the world so AutoWorldRegister sees it."""
    import ModuleUpdate
    import worlds
    from worlds import AutoWorldRegister

    if game_name in AutoWorldRegister.world_types:
        return
    ModuleUpdate.install_worlds([module])
    source = worlds.WorldSource(f"worlds.{module}")
    if not source.load() or game_name not in AutoWorldRegister.world_types:
        from mwgg_gui.yaml_creator.world_data import WorldDataError
        raise WorldDataError(
            f"Could not load the world for '{game_name}'. "
            "It may be unavailable for mobile (native extension or missing wheel) — see the log."
        )


def load_world_data_in_process(game_name: str, visibility: str = "simple",
                               module: str = "") -> dict:
    """Mobile counterpart of world_data.load_world_data — same payload, same
    WorldDataError contract, no subprocess."""
    import traceback

    from mwgg_gui.yaml_creator.world_data import WorldDataError

    try:
        import Generate
        import Options
        from mwgg_igdb import GameIndex
        from worlds import AutoWorldRegister

        if not module:
            module = GameIndex.game_names.get(game_name)
        if module is None:
            raise WorldDataError(
                f"'{game_name}' is not in the game index; it can't be installed or loaded."
            )

        _ensure_world_loaded(game_name, module)
        world = AutoWorldRegister.world_types[game_name]

        visibility_flag = (
            Options.Visibility.complex_ui
            if visibility == "complex"
            else Options.Visibility.simple_ui
        )
        option_groups = Options.get_option_groups(world, visibility_level=visibility_flag)

        groups_out: dict[str, list] = {}
        for group_name, options in option_groups.items():
            descs = []
            for option_name, option_class in (options or {}).items():
                try:
                    descs.append(Generate._y_describe_option(option_name, option_class))
                except Exception as e:
                    logger.warning("describe_option(%s) failed: %s", option_name, e)
            if descs:
                groups_out[group_name] = descs

        return {
            "ok": True,
            "game_name": game_name,
            "world": Generate._y_describe_world(world),
            "groups": groups_out,
        }
    except WorldDataError:
        raise
    except Exception as e:
        logger.error("in-process yaml options failed", exc_info=True)
        raise WorldDataError(f"{type(e).__name__}: {e}", trace=traceback.format_exc())
