#!/bin/bash
# One-time Mac setup: creates (or refreshes) ~/Desktop/fright-fued with all project
# files, and a Desktop "Fright Feud" shortcut with the pumpkin icon. The shortcut
# runs "Launch Fright Feud.command", which gets the latest version and opens the game.
# Run with:
#   curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/main/scripts/mac-desktop-setup.sh | bash
set -eu
BRANCH="main"
TARBALL="https://codeload.github.com/yongk802/fright-fued/tar.gz/refs/heads/$BRANCH"
FOLDER="$HOME/Desktop/fright-fued"

# An existing Fright Feud folder is updated in place (files you added are kept).
# Anything else is left untouched.
if [ -e "$FOLDER" ] && { [ -L "$FOLDER" ] || ! grep -q '"id": *"fright-feud"' "$FOLDER/app.json" 2>/dev/null; }; then
  echo "$FOLDER already exists and is not a Fright Feud folder; it was left untouched."
  echo "Rename or move it, then run this again."
  exit 1
fi

if [ ! -e "$FOLDER" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "$TARBALL" -o "$TMP/latest.tar.gz"
  mkdir "$TMP/new"
  tar -xzf "$TMP/latest.tar.gz" -C "$TMP/new" --strip-components 1
  grep -q '"id": *"fright-feud"' "$TMP/new/app.json"
  mv "$TMP/new" "$FOLDER"
  echo "Created $FOLDER"
fi

# Older folders may not have the update script yet; fetch it first.
if [ ! -f "$FOLDER/scripts/mac-update.sh" ]; then
  mkdir -p "$FOLDER/scripts"
  curl -fsSL "https://raw.githubusercontent.com/yongk802/fright-fued/$BRANCH/scripts/mac-update.sh" -o "$FOLDER/scripts/mac-update.sh"
fi
bash "$FOLDER/scripts/mac-update.sh"

echo
echo "Done. Double-click 'Fright Feud' on your Desktop to get the latest version and play."
open "$FOLDER" 2>/dev/null || true
