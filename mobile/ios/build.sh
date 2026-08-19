#!/usr/bin/env bash
# kivy-ios build for the MultiworldGG mobile app (EXPERIMENTAL).
#
# Known gap: kivy-ios' python3 recipe currently builds CPython 3.11.x while
# the project targets >= 3.13. The vendored code may use newer syntax/stdlib;
# treat failures here as expected until kivy-ios ships a newer recipe (or a
# custom recipe is added). Android (buildozer, CPython 3.14) is the primary
# mobile target.
#
# Requirements: macOS, Xcode (13+) with command line tools, brew deps:
#   brew install autoconf automake libtool pkg-config
# Run from the mobile/ directory after `python sync_vendor.py`.
set -euo pipefail

APP_NAME="mwggmobile"
MOBILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLCHAIN_DIR="${MOBILE_DIR}/ios/toolchain"

python3 -m pip install --upgrade kivy-ios

mkdir -p "${TOOLCHAIN_DIR}"
cd "${TOOLCHAIN_DIR}"

# Compiled recipes
toolchain build python3 kivy pillow numpy

# Pure-python deps (mirror buildozer.spec requirements)
toolchain pip install \
    "https://github.com/kivymd/KivyMD/archive/d2f7740.zip" \
    materialyoucolor exceptiongroup asyncgui asynckivy \
    websockets pyyaml requests certifi nest_asyncio \
    packaging platformdirs pathspec typing_extensions pygments colorama

# Create/update the Xcode project pointing at the app tree (main.py dir)
if [ ! -d "${APP_NAME}-ios" ]; then
    toolchain create "${APP_NAME}" "${MOBILE_DIR}"
else
    toolchain update "${APP_NAME}-ios"
fi

# Unsigned simulator build (CI artifact / local smoke)
xcodebuild -project "${APP_NAME}-ios/${APP_NAME}.xcodeproj" \
    -scheme "${APP_NAME}" \
    -sdk iphonesimulator \
    -configuration Debug \
    CODE_SIGNING_ALLOWED=NO \
    build

echo "iOS simulator build complete: ${TOOLCHAIN_DIR}/${APP_NAME}-ios"
