"""Shell-specific Kivy bootstrap.

The GUI package serves two shells: the MultiworldGG desktop launcher
(MultiWorld.py) and the mobile app (mobile/main.py in this repo). Window
geometry, input providers, and titlebar chrome are shell decisions, not GUI
decisions, so they live here instead of at the top of app.py.

The shell is selected by the MWGG_SHELL environment variable ("desktop" when
unset — the monorepo launcher needs no change; the mobile entry point sets
"mobile" before importing mwgg_gui.app).

Ordering contract: configure_shell() touches only kivy.config and must run
before kivy.core.window is imported; apply_window_chrome(Window) runs
immediately after that import. app.py calls both at the same points in its
import sequence where the equivalent statements used to live.
"""
import os
import sys

_SHELL_ENV = "MWGG_SHELL"


def shell_name() -> str:
    return os.environ.get(_SHELL_ENV, "desktop")


def is_mobile_shell() -> bool:
    return shell_name() == "mobile"


def is_desktop_shell() -> bool:
    return not is_mobile_shell()


def _set_default_font(config, fonts_dir: str) -> None:
    config.set("kivy", "default_font", ["Inter",
                                        os.path.join(fonts_dir, "Inter-Regular.ttf"),
                                        os.path.join(fonts_dir, "Inter-Italic.ttf"),
                                        os.path.join(fonts_dir, "Inter-Bold.ttf"),
                                        os.path.join(fonts_dir, "Inter-BoldItalic.ttf")])


def _configure_desktop(config) -> None:
    config.set("input", "mouse", "mouse,disable_multitouch")
    config.set("kivy", "exit_on_escape", "0")
    # CWD-relative on purpose: the desktop launcher runs from the MultiworldGG
    # root, where data/fonts/ lives (KIVY_DATA_DIR/fonts has the same files,
    # but the persisted kivy.ini predates that and changing the written value
    # would churn every install's config).
    _set_default_font(config, os.path.join("data", "fonts"))
    config.set("graphics", "width", "1099")
    config.set("graphics", "height", "699")
    # custom_titlebar is Windows-only: Kivy's set_custom_titlebar() only succeeds
    # there, and we explicitly write "0" on other platforms to overwrite any value
    # persisted by a previous Windows-only run (config.write() persists to
    # KIVY_HOME, so a one-time misconfig sticks across runs otherwise).
    config.set("graphics", "custom_titlebar", "1" if sys.platform == "win32" else "0")
    config.set("graphics", "minimum_height", "700")
    config.set("graphics", "minimum_width", "600")
    config.set("graphics", "focus", "False")
    config.write()


def _configure_mobile(config) -> None:
    # No window geometry, no input-provider override (multitouch must stay
    # available), no custom titlebar. The OS owns the window on Android/iOS.
    config.set("kivy", "exit_on_escape", "0")
    config.set("graphics", "custom_titlebar", "0")
    data_dir = os.environ.get("KIVY_DATA_DIR", "")
    if data_dir:
        _set_default_font(config, os.path.join(data_dir, "fonts"))
    config.write()


def configure_shell(config) -> None:
    """Apply shell-specific kivy.config settings. Must run before
    kivy.core.window is imported."""
    if is_mobile_shell():
        _configure_mobile(config)
    else:
        _configure_desktop(config)


def apply_window_chrome(window) -> None:
    """Apply shell-specific Window properties, immediately after the
    kivy.core.window import."""
    if is_mobile_shell():
        window.clearcolor = [0, 0, 0, 1]
        # Keep the text input above the soft keyboard; harmless elsewhere.
        window.softinput_mode = "below_target"
        return
    # Windows-only: hide the window during the splash sequence so the splash
    # process owns the visible UI until Kivy finishes loading (see MultiWorld.py
    # for the splash gate). Borderless is also Windows-only because the custom
    # titlebar Kivy uses to replace the system one only works on Windows — on
    # Mac/Linux it silently fails ("Window: Window.custom_titlebar not set to
    # True… can't set custom titlebar"), leaving a borderless window with no
    # titlebar at all (no drag, no close button). Additionally on WSLg/llvmpipe
    # the opacity=0 + transparent clearcolor combo causes EffectWidget FBO
    # creation to fail at first layout (GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT),
    # which kills the Kivy main loop right after "Added nav_layout to screen".
    if sys.platform == "win32":
        window.opacity = 0
        window.clearcolor = [0, 0, 0, 0]
        window.borderless = True
    else:
        window.clearcolor = [0, 0, 0, 1]
