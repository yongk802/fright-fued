#!/bin/bash
# Double-click to launch Fright Feud. It starts App Engine if needed and opens the
# game in your browser.
APP="$HOME/Applications/Fright Feud.app"
if [ -d "$APP" ]; then
  open "$APP"
  exit 0
fi
# Not installed yet: open the app from the downloaded ZIP so it can install itself.
for candidate in "$HOME/Downloads/Fright Feud.app" "$HOME/Downloads/Fright-Feud-macOS/Fright Feud.app" \
                 "$HOME/Desktop/Fright Feud.app"; do
  if [ -d "$candidate" ]; then
    echo "First launch: opening $candidate so it can install itself."
    echo "If macOS blocks it, Control-click the app in Finder and choose Open."
    open "$candidate"
    exit 0
  fi
done
echo "Fright Feud.app was not found."
echo "Unzip Fright-Feud-macOS.zip in Downloads, Control-click Fright Feud.app, choose Open,"
echo "then use this launcher from then on."
read -r -p "Press Return to close." _
