---
name: desktop-folder
description: Package the Fright Feud project as a fright-fued folder the user can put on their Mac Desktop, and explain the Desktop shortcut/updater. Use when the user asks for the project files, a fright-fued folder, a copy on their desktop, a download of the game, or a desktop shortcut/launcher.
---

# Fright Feud folder for the user's Desktop

This session runs in a cloud container. It cannot write to the user's Mac, create
Desktop icons, or launch apps there. Say so plainly, then deliver a download that
becomes the folder in one double-click.

## Build the folder ZIP

```sh
S=<your scratchpad directory>
python3 scripts/package.py --prefix fright-fued --output "$S/fright-fued.zip"
python3 -c "import sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);assert z.testzip() is None;n=z.namelist();assert all(x.startswith('fright-fued/') for x in n) and 'fright-fued/index.html' in n and 'fright-fued/app.json' in n;print(len(n),'files OK')" "$S/fright-fued.zip"
```

- Build from the committed state of the working branch; mention any uncommitted
  changes before packaging.
- `package.py` already excludes `.git`, virtual environments, caches and
  screenshots. Do not hand-assemble the ZIP.
- Write the ZIP to the scratchpad, never into the repo (`dist/` is gitignored but
  the scratchpad keeps the checkout clean).
- Without `--prefix`, `package.py` makes the App Engine static ZIP (`app.json` at the
  root). Keep that default unchanged; it is a different deliverable.

## Deliver

Send it with `SendUserFile` (`display: "attach"`), then tell the user:

1. Download **fright-fued.zip** and drag it onto the Desktop.
2. Double-click it; Finder creates a **fright-fued** folder. The ZIP can then be deleted.

Be honest about what was verified: the ZIP was checked in the cloud, not on a Mac.

## Explain how this folder relates to the playable game

- The folder is a snapshot. It does not update by itself; ask for a new ZIP, or use
  GitHub's **Code → Download ZIP** on the working branch.
- Fright Feud.app plays the installed copy under
  `~/Library/Application Support/Fright Feud/apps/fright-feud` (or
  `~/git/personal-apps/fright-feud` when it reuses an existing engine). Editing the
  Desktop folder does not change the game.
- Pushed changes reach the installed game through **Update Fright Feud.command**
  followed by Cmd-R in the game tab. It replaces `index.html` and `app.json` and
  keeps backups under `~/Library/Application Support/Fright Feud/backups`.

## Desktop folder with launcher and updater (preferred)

A ZIP alone does not create anything on the Desktop. The reliable path is one
Terminal paste that creates `~/Desktop/fright-fued` with every project file and the
repo-root executables `Launch Fright Feud.command` and `Get Latest Updates.command`:

```sh
curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/<branch>/scripts/mac-desktop-setup.sh | bash
```

Replace `<branch>` with the branch the `BRANCH=` lines point at. The updater
refreshes the Desktop folder and copies `index.html`, `app.json` and `fonts/` into
the installed game, with backups. Keep both `.command` files executable in git
(mode 755). If the working branch changes, update `BRANCH=` in
`scripts/mac-desktop-setup.sh` and `Get Latest Updates.command` and the URLs in
`README.md` and here, commit, push, and have the user
re-run the command. Test script changes with a temporary `HOME` and stubs for
`open`/`osascript` on `PATH`; never touch real user directories.
