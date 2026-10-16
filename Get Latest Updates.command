#!/bin/bash
# Double-click to download the latest Fright Feud without launching it.
# (Launch Fright Feud.command also does this automatically every time.)
# The body is in braces so bash reads it fully before an update replaces this file.
{
FOLDER="$(cd "$(dirname "$0")" && pwd)"
bash "$FOLDER/scripts/mac-update.sh"
echo
echo "If the game is already open, refresh its browser tab (Command-R)."
read -r -p "Press Return to close." _
exit 0
}
