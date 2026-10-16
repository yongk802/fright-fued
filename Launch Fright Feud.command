#!/bin/bash
# Double-click (or use the Desktop "Fright Feud" shortcut) to play.
# Every launch first gets the latest version from GitHub, then opens the game.
# Before the first install, it finds the downloaded app (or its ZIP) and opens it
# through macOS's normal first-open approval.
# The body is in braces so bash reads it fully before an update replaces this file.
{
FOLDER="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/Fright Feud.app"
BUNDLE_ID="com.yongk802.fright-feud"
RELEASE="https://github.com/yongk802/fright-fued/releases/download/v1.2.1/Fright-Feud-macOS.zip"

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

# 1. Get the latest version (keeps playing the current one if this fails).
if ! bash "$FOLDER/scripts/mac-update.sh"; then
  echo "Starting the version already installed."
fi
echo

# 2. Launch. The app opens the game in a new browser tab and then quits, so
#    every launch shows the newest files.
if [ -d "$APP" ]; then
  echo "Opening Fright Feud…"
  ARCH="$(uname -m)"
  PYTHON="$APP/Contents/Resources/runtimes/$ARCH/python/bin/python3.12"
  if [ -x "$PYTHON" ] && [ -f "$FOLDER/scripts/launch_phone.py" ]; then
    if ! "$PYTHON" -I -B "$FOLDER/scripts/launch_phone.py" --app "$APP"; then
      echo "The phone connection could not start. Opening the local game instead."
      open "$APP"
      finish
    fi
  else
    open "$APP"
    sleep 2
  fi
  exit 0
fi

# Not installed yet: the app anywhere on this Mac (Spotlight), or the usual spots.
found="$(mdfind "kMDItemCFBundleIdentifier == '$BUNDLE_ID'" 2>/dev/null | grep -v '/\.Trash/' | head -n 1)"
for candidate in "$found" "$HOME/Downloads/Fright Feud.app" "$HOME/Desktop/Fright Feud.app" \
                 "$HOME/Downloads/Fright-Feud-macOS/Fright Feud.app" "/Applications/Fright Feud.app"; do
  if [ -n "$candidate" ] && [ -d "$candidate" ]; then
    first_open "$candidate"
  fi
done

# The downloaded ZIP: unzip it with Archive Utility (as a Finder double-click does).
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

echo "Fright Feud.app isn't on this Mac yet. Opening the download in your browser…"
open "$RELEASE"
echo
echo "When the download finishes, double-click this launcher again."
finish
}
