# MultiworldGG Mobile

Mobile shell for the `mwgg_gui` package: Android via buildozer, iOS via
kivy-ios (experimental). Scope is client-only — launcher, console, hints,
yaml creator; games run as text clients or Universal Tracker. No generation,
no server hosting, no patching on device.

## Layout

```
main.py            entry point (mobile analog of the monorepo's MultiWorld.py)
shims/             modules that SHADOW monorepo modules on sys.path:
  ModuleUpdate.py    world store — downloads pure-python world wheels from the
                     game index and extracts them into app storage (no pip/uv)
  MultiServer.py     CommandProcessor/mark_raw only (no server, no sqlalchemy)
  jellyfish.py       pure-python damerau_levenshtein_distance
vendor/            assembled by sync_vendor.py (gitignored):
                   mwgg_gui + monorepo module slice + data assets
buildozer.spec     Android build (p4a develop -> CPython 3.14)
ios/build.sh       kivy-ios simulator build (CPython 3.11 — see caveat inside)
check_imports.py   import smoke test, sandboxed (CI: mobile-imports workflow)
sync_vendor.py     vendor-tree assembly + import-closure check
```

## Building locally

Android builds need Linux (WSL2 works). iOS builds need macOS + Xcode.
The practical path on Windows is CI: the `mobile-android` workflow
(manual dispatch or version tags) uploads the APK artifact.

```bash
# 1. assemble the vendor tree (any OS; needs a MultiworldGG checkout)
python mobile/sync_vendor.py --monorepo /path/to/MultiworldGG/src

# 2. sanity-check imports (needs the desktop kivy/kivymd env)
python mobile/check_imports.py

# 3. Android (Linux/WSL only)
cd mobile && buildozer android debug
```

## CI

| Workflow | Trigger | What |
|---|---|---|
| `mobile-imports` | PRs/pushes touching `mwgg_gui/` or `mobile/` | vendor sync + full import smoke under xvfb |
| `mobile-android` | manual / `v*` tags | buildozer APK artifact |
| `mobile-ios` | manual / `v*` tags | kivy-ios simulator build (continue-on-error) |

All three check out the monorepo from `MultiworldGG/MultiworldGG-Beta`
(`MONOREPO_REPO` env at the top of each workflow — adjust if the canonical
repo differs). If that repo is private, add a read-scoped PAT as the
`MWGG_MONOREPO_TOKEN` secret.

## How worlds get on the device

The game index (`mwgg_igdb`, bundled at build time) maps each game to a
`worlds.<slug>` pure-python wheel URL. The `ModuleUpdate` shim downloads the
wheel, verifies its sha256 fragment, rejects non-pure wheels, and extracts
payload + dist-info into `mwgg_venv_site_packages()` inside the app sandbox —
the same path layout the desktop worlds venv uses, so `worlds/__init__`,
`importlib.metadata`, and `Utils.set_game_names` all behave exactly as on
desktop. Hand-dropped `.apworld` files in the sandbox `custom_worlds/` dir
keep working through the existing zipimport path.

Worlds with native extensions (`.so`/`.pyd` in the wheel) are rejected with a
clear error — there is no compiler on device.

## Known gaps / follow-ups

- iOS: kivy-ios builds CPython 3.11 vs the project's >= 3.13 target; the iOS
  workflow stays continue-on-error until the toolchain catches up.
- Age-rating index variants (`set_age_filter`) can't swap the bundled
  `mwgg_igdb` snapshot at runtime yet.
- Safe-area insets (notches) default to 0; first builds run non-fullscreen.
