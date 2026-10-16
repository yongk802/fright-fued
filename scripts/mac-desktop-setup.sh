#!/bin/bash
# One-time Mac setup: puts two items on the Desktop.
#   "Fright Feud"                  - alias to the installed ~/Applications/Fright Feud.app
#   "Update Fright Feud.command"   - downloads the latest game file from the working
#                                    branch into the installed game, keeping a backup.
# Run with:
#   curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/claude/ecstatic-dijkstra-hiijnn/scripts/mac-desktop-setup.sh | bash
set -eu

APP="$HOME/Applications/Fright Feud.app"
DESKTOP="$HOME/Desktop"

if [ ! -d "$APP" ]; then
  echo "Fright Feud.app is not installed at $APP yet."
  echo "Open the Fright Feud.app from the downloaded ZIP once (Control-click > Open), then run this again."
  exit 1
fi

if [ ! -e "$DESKTOP/Fright Feud" ]; then
  osascript -e "tell application \"Finder\" to make alias file to (POSIX file \"$APP\") at (POSIX file \"$DESKTOP\")" >/dev/null
  echo "Added Desktop shortcut: Fright Feud"
else
  echo "Desktop shortcut already exists: Fright Feud"
fi

UPDATER="$DESKTOP/Update Fright Feud.command"
cat > "$UPDATER" <<'UPDATER_EOF'
#!/bin/bash
# Downloads the latest Fright Feud game from GitHub into the installed copy.
set -eu
BRANCH="claude/ecstatic-dijkstra-hiijnn"
BASE="https://raw.githubusercontent.com/yongk802/fright-fued/$BRANCH"

TARGET=""
for dir in "$HOME/Library/Application Support/Fright Feud/apps/fright-feud" \
           "$HOME/git/personal-apps/fright-feud"; do
  if [ -d "$dir" ] && [ ! -L "$dir" ] && grep -q '"id": *"fright-feud"' "$dir/app.json" 2>/dev/null; then
    TARGET="$dir"; break
  fi
done
if [ -z "$TARGET" ]; then
  echo "Could not find the installed game. Open Fright Feud from the Desktop once, then try again."
  read -r -p "Press Return to close." _; exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for f in index.html app.json; do
  # The query string skips GitHub's few-minute raw-file cache.
  if ! curl -fsSL "$BASE/$f?nocache=$(date +%s)" -o "$TMP/$f"; then
    echo "Could not download $f from GitHub; nothing was changed. Check the internet connection."
    read -r -p "Press Return to close." _; exit 1
  fi
done
if ! grep -q "Fright Feud" "$TMP/index.html" || ! grep -q '"id": *"fright-feud"' "$TMP/app.json"; then
  echo "The download did not look like Fright Feud; nothing was changed."
  read -r -p "Press Return to close." _; exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$HOME/Library/Application Support/Fright Feud/backups/$STAMP"
mkdir -p "$BACKUPS"
cp "$TARGET/index.html" "$TARGET/app.json" "$BACKUPS/"
cp "$TMP/index.html" "$TMP/app.json" "$TARGET/"
echo "Updated $TARGET"
echo "Previous version saved in $BACKUPS"
echo "Now refresh the Fright Feud browser tab (Command-R)."
read -r -p "Press Return to close." _
UPDATER_EOF
chmod +x "$UPDATER"
echo "Added Desktop updater: Update Fright Feud.command"
echo "Done. Double-click 'Fright Feud' on your Desktop to play."
