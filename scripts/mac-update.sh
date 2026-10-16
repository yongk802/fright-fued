#!/bin/bash
# Downloads the latest Fright Feud from GitHub (main branch) and installs it:
#   - refreshes the Desktop fright-fued folder (files you added are kept)
#   - copies the game files into the copy Fright Feud.app plays
#   - keeps the Desktop "Fright Feud" shortcut (with the pumpkin icon) in place
# Backups go to ~/Library/Application Support/Fright Feud/backups.
# Exit status: 0 updated, 1 failed (nothing changed). Used by both .command files.
# The body is in braces so bash reads it fully before an update replaces this file.
{
set -u
BRANCH="main"
TARBALL="https://codeload.github.com/yongk802/fright-fued/tar.gz/refs/heads/$BRANCH"
FOLDER="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/Fright Feud"
GAME_ITEMS="index.html app.json fonts assets"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Getting the latest Fright Feud from GitHub…"
if ! curl -fsSL --connect-timeout 10 --max-time 120 "$TARBALL" -o "$TMP/latest.tar.gz" \
   || ! mkdir "$TMP/new" || ! tar -xzf "$TMP/latest.tar.gz" -C "$TMP/new" --strip-components 1; then
  echo "Could not download the update (no internet?). Nothing was changed."
  exit 1
fi
if ! grep -q '"id": *"fright-feud"' "$TMP/new/app.json" 2>/dev/null || [ ! -f "$TMP/new/index.html" ]; then
  echo "The download did not look like Fright Feud. Nothing was changed."
  exit 1
fi

BACKUP="$SUPPORT/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
# Keep only the 10 newest backups.
ls -1d "$SUPPORT/backups"/*/ 2>/dev/null | sort -r | tail -n +11 | while read -r old; do rm -rf "$old"; done

cp -R "$FOLDER" "$BACKUP/desktop-folder"
cp -R "$TMP/new/." "$FOLDER/"
echo "Updated the folder: $FOLDER"

GAME=""
for dir in "$SUPPORT/apps/fright-feud" "$HOME/git/personal-apps/fright-feud"; do
  if [ -d "$dir" ] && [ ! -L "$dir" ] && grep -q '"id": *"fright-feud"' "$dir/app.json" 2>/dev/null; then
    GAME="$dir"; break
  fi
done
if [ -n "$GAME" ]; then
  mkdir -p "$BACKUP/installed-game"
  cp -R "$GAME/." "$BACKUP/installed-game/"
  for item in $GAME_ITEMS; do
    if [ -d "$TMP/new/$item" ]; then
      mkdir -p "$GAME/$item" && cp -R "$TMP/new/$item/." "$GAME/$item/"
    elif [ -f "$TMP/new/$item" ]; then
      cp "$TMP/new/$item" "$GAME/$item"
    fi
  done
  echo "Updated the installed game: $GAME"
else
  echo "The game isn't installed yet. The app installs its built-in version when it"
  echo "first opens; launch once more afterwards to get the latest changes."
fi
echo "Previous versions saved in: $BACKUP"

# Desktop shortcut to the launcher, with the pumpkin icon. Never touches the app
# itself (a custom icon inside the signed app would break its signature).
SHORTCUT="$HOME/Desktop/Fright Feud"
LAUNCHER="$FOLDER/Launch Fright Feud.command"
ICON="$FOLDER/icon/Fright Feud Icon.png"
if command -v osascript >/dev/null 2>&1; then
  if [ ! -e "$SHORTCUT" ]; then
    osascript -e "tell application \"Finder\" to make alias file to (POSIX file \"$LAUNCHER\") at (POSIX file \"$HOME/Desktop\") with properties {name:\"Fright Feud\"}" >/dev/null 2>&1 \
      && echo "Added the Desktop shortcut: Fright Feud"
  fi
  if [ -e "$SHORTCUT" ] && [ -f "$ICON" ]; then
    osascript -l JavaScript -e "ObjC.import('AppKit'); var i=\$.NSImage.alloc.initWithContentsOfFile('$ICON'); \$.NSWorkspace.sharedWorkspace.setIconForFileOptions(i, '$SHORTCUT', 0);" >/dev/null 2>&1 || true
  fi
fi
exit 0
}
