#!/bin/bash
# One-time Mac setup: creates ~/Desktop/fright-fued with all project files plus
#   "Launch Fright Feud.command"  - starts the game
#   "Get Latest Updates.command"  - downloads the latest version from GitHub
# Run with:
#   curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/claude/ecstatic-dijkstra-hiijnn/scripts/mac-desktop-setup.sh | bash
set -eu
BRANCH="claude/ecstatic-dijkstra-hiijnn"
TARBALL="https://codeload.github.com/yongk802/fright-fued/tar.gz/refs/heads/$BRANCH"
FOLDER="$HOME/Desktop/fright-fued"

# An existing Fright Feud folder (for example, unzipped from fright-fued.zip) is
# updated in place; files you added are kept. Anything else is left untouched.
if [ -e "$FOLDER" ] && { [ -L "$FOLDER" ] || ! grep -q '"id": *"fright-feud"' "$FOLDER/app.json" 2>/dev/null; }; then
  echo "$FOLDER already exists and is not a Fright Feud folder; it was left untouched."
  echo "Rename or move it, then run this again."
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$TARBALL" -o "$TMP/latest.tar.gz"
mkdir "$TMP/new"
tar -xzf "$TMP/latest.tar.gz" -C "$TMP/new" --strip-components 1
grep -q '"id": *"fright-feud"' "$TMP/new/app.json"
[ -x "$TMP/new/Launch Fright Feud.command" ] && [ -x "$TMP/new/Get Latest Updates.command" ]
if [ -e "$FOLDER" ]; then
  cp -R "$TMP/new/." "$FOLDER/"
  echo "Added the latest files and launchers to the existing $FOLDER"
else
  mv "$TMP/new" "$FOLDER"
  echo "Created $FOLDER"
fi

# An app-icon shortcut inside the folder, once the app is installed.
APP="$HOME/Applications/Fright Feud.app"
if [ -d "$APP" ] && [ ! -e "$FOLDER/Fright Feud" ]; then
  osascript -e "tell application \"Finder\" to make alias file to (POSIX file \"$APP\") at (POSIX file \"$FOLDER\")" >/dev/null 2>&1 \
    && echo "  Fright Feud                  - app shortcut (double-click to play)"
fi

echo "  Launch Fright Feud.command  - double-click to play"
echo "  Get Latest Updates.command  - double-click to get the latest changes"
open "$FOLDER" 2>/dev/null || true
