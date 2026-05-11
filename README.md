# mwgg_gui

Kivy/KivyMD GUI package for MultiworldGG.

This repository contains the reusable MultiworldGG desktop UI package, including launcher, console, hint, settings, theme, and shared component modules.

## Status

This is a private package and is not intended for upload to a public package index.

## Why this is a separate package

`mwgg_gui` is shipped as a standalone Python package — separately versioned from the main MultiworldGG application — specifically to enable **UI hotfixes without rebuilding or re-releasing the full frozen executable**. A new release of `mwgg_gui` can be pulled into an installed MultiworldGG without touching the rest of the application.

The package is **not** intended to be importable standalone. At runtime it requires the MultiworldGG monorepo's `src/` directory to be on `sys.path`, because several modules import from monorepo top-level names (`Utils`, `NetUtils`, `BaseUtils`, `BaseClasses`, `CommonClient`, and — in `mwgg_gui.app` — also `MultiWorld` and `ModuleUpdate`). This implicit dependency is intentional and is not declared in `pyproject.toml`; the package is designed to be consumed by the MultiworldGG runtime, not by arbitrary Kivy apps.

## Requirements

- Python >= 3.13
- Kivy >= 2.3.1
- KivyMD from the configured GitHub revision in `pyproject.toml`

Install for local development from the repository root:

```powershell
python -m pip install -e .
```

## Package Data

Kivy `.kv` files are included as package data through `pyproject.toml`.

## License

MultiworldGG GUI code is distributed under the license in `LICENSE`.

The original upstream license notice is preserved in `LICENSE-original.md`.
