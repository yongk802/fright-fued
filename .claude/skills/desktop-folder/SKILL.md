---
name: desktop-folder
description: Set up or repair the user's Mac Desktop fright-fued folder, the Desktop "Fright Feud" shortcut (pumpkin icon) that auto-updates and launches the game, the downloadable icon, or a ZIP of the project. Use when the user asks for project files, a desktop folder/shortcut/launcher/icon, or says launching or updating on their Mac does not work.
---

# The user's Mac Desktop setup

This session runs in a cloud container. It cannot write to the user's Mac, create
Desktop icons, or launch apps there. Say so plainly and give one Terminal paste
instead. Game changes themselves are shipped with the `update-game` skill.

## What is on the Mac

- `~/Desktop/fright-fued/`: every repo file (from the `main` tarball), including
  - `Launch Fright Feud.command`: runs `scripts/mac-update.sh`, then opens
    `~/Applications/Fright Feud.app` (which opens the game in a new browser tab and
    quits). Offline, it plays the installed version. Before the first install it
    finds the app via Spotlight / Downloads, unzips a downloaded
    `Fright-Feud-macOS*.zip` with Archive Utility, or opens the release download.
  - `Get Latest Updates.command`: update only, no launch.
  - `icon/Fright Feud Icon.png` and `.icns`: the pumpkin icon.
- `~/Desktop/Fright Feud`: Finder alias to the launcher, given the pumpkin icon by
  `mac-update.sh` (JXA `NSWorkspace setIcon`). Never set a custom icon on
  `Fright Feud.app` itself; that writes inside the signed bundle.
- Installed game: `~/Library/Application Support/Fright Feud/apps/fright-feud` (or
  `~/git/personal-apps/fright-feud` when an existing engine is reused). The updater
  copies `index.html`, `app.json`, `fonts/`, `assets/` there. Backups (10 newest)
  are in `~/Library/Application Support/Fright Feud/backups`.

## Set up or repair (one Terminal paste)

```sh
curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/main/scripts/mac-desktop-setup.sh | bash
```

It creates the folder (or refreshes an existing Fright Feud folder, keeping added
files), runs the updater, and makes the Desktop shortcut. A folder that is not a
Fright Feud folder is left untouched. The app must be opened once (Control-click →
Open) for the first install; that is normal Gatekeeper approval, never bypass it.

## Icon by hand

Send `icon/Fright Feud Icon.png` with `SendUserFile`. To assign it: open the PNG in
Preview, Cmd-A, Cmd-C; select the Desktop shortcut, Cmd-I; click the small icon at
the top-left of the Info window; Cmd-V. Advise against pasting onto the app itself.

## Project ZIP

```sh
python3 scripts/package.py --prefix fright-fued --output "<scratchpad>/fright-fued.zip"
```
Verify with `zipfile` (testzip, every name under `fright-fued/`, the two `.command`
files mode 755), then `SendUserFile` with `display: "attach"`. A ZIP does not
create the Desktop shortcut; prefer the Terminal paste above.

## Changing these scripts

Keep `BRANCH="main"` in `scripts/mac-update.sh` and `scripts/mac-desktop-setup.sh`.
Scripts that may be replaced while running keep their whole body in `{ … }`.
Keep `.command` files mode 755 in git. Test with a temporary `HOME` and stub
`curl`/`open`/`osascript`/`mdfind` on `PATH` (a stub `curl` can serve a tarball made
from the working tree). Never touch real user directories.
