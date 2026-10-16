#!/bin/bash
# Double-click to launch Fright Feud. It starts App Engine if needed and opens the
# game in your browser. Before the first install, it finds the downloaded app (or
# its ZIP) and opens it through macOS's normal first-open approval.
APP="$HOME/Applications/Fright Feud.app"
BUNDLE_ID="com.yongk802.fright-feud"
RELEASE="https://github.com/yongk802/fright-fued/releases/download/v1.1.0/Fright-Feud-macOS.zip"

finish() { echo; read -r -p "Press Return to close." _; exit 0; }

first_open() {
  echo "First launch: opening $1 so it can install itself."
  echo
  echo "If macOS says it can't be opened, a Finder window is showing the app:"
  echo "Control-click 'Fright Feud.app', choose Open, then click Open."
  open -R "$1"
  open "$1"
  finish
}

if [ -d "$APP" ]; then
  open "$APP"
  exit 0
fi

# 1. The app anywhere on this Mac (Spotlight), or in the usual download spots.
found="$(mdfind "kMDItemCFBundleIdentifier == '$BUNDLE_ID'" 2>/dev/null | grep -v '/\.Trash/' | head -n 1)"
for candidate in "$found" "$HOME/Downloads/Fright Feud.app" "$HOME/Desktop/Fright Feud.app" \
                 "$HOME/Downloads/Fright-Feud-macOS/Fright Feud.app" "/Applications/Fright Feud.app"; do
  if [ -n "$candidate" ] && [ -d "$candidate" ]; then
    first_open "$candidate"
  fi
done

# 2. The downloaded ZIP: unzip it with Archive Utility (as a Finder double-click does).
zip="$(ls -t "$HOME/Downloads"/Fright-Feud-macOS*.zip 2>/dev/null | head -n 1)"
if [ -n "$zip" ]; then
  echo "Unzipping $zip…"
  open -a "Archive Utility" "$zip"
  for _ in $(seq 1 60); do
    if [ -d "$HOME/Downloads/Fright Feud.app" ]; then
      sleep 1
      first_open "$HOME/Downloads/Fright Feud.app"
    fi
    sleep 1
  done
  echo "The ZIP did not unzip to Downloads/Fright Feud.app."
  echo "Double-click $zip in Finder, then double-click this launcher again."
  finish
fi

# 3. Nothing downloaded yet: download it in the browser as usual.
echo "Fright Feud.app isn't on this Mac yet. Opening the download in your browser…"
open "$RELEASE"
echo
echo "When the download finishes, double-click this launcher again."
finish
