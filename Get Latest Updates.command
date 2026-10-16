#!/bin/bash
# Double-click to download the latest Fright Feud from GitHub.
# Updates this folder and the game that Fright Feud.app plays, keeping backups.
# The whole body is in braces so bash reads it fully before this file is replaced.
{
set -u
BRANCH="claude/ecstatic-dijkstra-hiijnn"
TARBALL="https://codeload.github.com/yongk802/fright-fued/tar.gz/refs/heads/$BRANCH"
FOLDER="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/Fright Feud"

finish() { echo; read -r -p "Press Return to close." _; exit "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Downloading the latest Fright Feud…"
if ! curl -fsSL "$TARBALL" -o "$TMP/latest.tar.gz" \
   || ! mkdir "$TMP/new" || ! tar -xzf "$TMP/latest.tar.gz" -C "$TMP/new" --strip-components 1; then
  echo "The download failed; nothing was changed. Check the internet connection."
  finish 1
fi
if ! grep -q '"id": *"fright-feud"' "$TMP/new/app.json" 2>/dev/null || [ ! -f "$TMP/new/index.html" ]; then
  echo "The download did not look like Fright Feud; nothing was changed."
  finish 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$SUPPORT/backups/$STAMP"
mkdir -p "$BACKUP"

# This folder: back it up, then copy new files over it (extra files you added stay).
cp -R "$FOLDER" "$BACKUP/desktop-folder"
cp -R "$TMP/new/." "$FOLDER/"
echo "Updated $FOLDER"

# The installed game that Fright Feud.app serves.
GAME=""
for dir in "$SUPPORT/apps/fright-feud" "$HOME/git/personal-apps/fright-feud"; do
  if [ -d "$dir" ] && [ ! -L "$dir" ] && grep -q '"id": *"fright-feud"' "$dir/app.json" 2>/dev/null; then
    GAME="$dir"; break
  fi
done
if [ -n "$GAME" ]; then
  mkdir -p "$BACKUP/installed-game"
  cp -R "$GAME/." "$BACKUP/installed-game/"
  cp "$TMP/new/index.html" "$TMP/new/app.json" "$GAME/"
  cp -R "$TMP/new/fonts/." "$GAME/fonts/"
  echo "Updated the installed game: $GAME"
  echo
  echo "Now refresh the Fright Feud browser tab (Command-R)."
else
  echo
  echo "The game isn't installed yet. Double-click 'Launch Fright Feud.command' first."
fi
echo "Previous versions are saved in: $BACKUP"
finish 0
}
