[app]
title = MultiworldGG
package.name = mwggmobile
package.domain = gg.multiworld

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,ttf,otf,txt,json,atlas,ini,yaml,zip
# Files without extensions / special cases inside the vendor tree
source.include_patterns = vendor/LICENSE,vendor/data/*,vendor/kivy_data/*
source.exclude_dirs = bin,.buildozer,ios
source.exclude_patterns = sync_vendor.py,check_imports.py

version = 0.1.0

# Pure-python pins follow the desktop environment:
#  - KivyMD is the same commit pyproject.toml pins (d2f7740)
#  - materialyoucolor/exceptiongroup/asyncgui/asynckivy are KivyMD 2.x deps
#  - pygments: mwgg_gui.yaml_creator syntax highlighting
#  - packaging/platformdirs/pathspec/typing_extensions/websockets/pyyaml/
#    requests/certifi/nest_asyncio: vendored monorepo runtime deps
requirements = python3,kivy==2.3.1,https://github.com/kivymd/KivyMD/archive/d2f7740.zip,materialyoucolor,exceptiongroup,asyncgui,asynckivy,pillow,numpy,websockets,pyyaml,requests,certifi,nest_asyncio,packaging,platformdirs,pathspec,typing_extensions,pygments,colorama

icon.filename = %(source.dir)s/vendor/data/icon.png
presplash.filename = %(source.dir)s/vendor/data/icon.png

# Responsive layout handles both orientations (LayoutMode size classes).
orientation = all
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = True

# python-for-android: develop builds CPython 3.14, which satisfies the
# project's requires-python >= 3.13 (release v2026.05.09 or later also works).
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
