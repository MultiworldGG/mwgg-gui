# mwgg_gui

Kivy/KivyMD GUI package for MultiworldGG.

This repository contains the reusable MultiworldGG desktop UI package, including launcher, console, hint, settings, theme, and shared component modules.

## Status

This is a private package and is not intended for upload to a public package index.

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
