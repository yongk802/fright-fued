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

if [ -e "$FOLDER" ]; then
  if [ -x "$FOLDER/Get Latest Updates.command" ]; then
    echo "$FOLDER already exists. Double-click 'Get Latest Updates.command' in it to update."
  else
    echo "$FOLDER already exists and was not made by this setup; it was left untouched."
    echo "Rename or move it, then run this again."
  fi
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$TARBALL" -o "$TMP/latest.tar.gz"
mkdir "$TMP/new"
tar -xzf "$TMP/latest.tar.gz" -C "$TMP/new" --strip-components 1
grep -q '"id": *"fright-feud"' "$TMP/new/app.json"
[ -x "$TMP/new/Launch Fright Feud.command" ] && [ -x "$TMP/new/Get Latest Updates.command" ]
mv "$TMP/new" "$FOLDER"

echo "Created $FOLDER"
echo "  Launch Fright Feud.command  - double-click to play"
echo "  Get Latest Updates.command  - double-click to get the latest changes"
open "$FOLDER" 2>/dev/null || true
