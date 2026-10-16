---
name: update-game
description: Make a change the user asks for in the Fright Feud game (questions, rounds, look, sounds, splash, behavior), test it, and ship it straight to the main branch so the user's Desktop "Fright Feud" shortcut picks it up on the next launch. Use for any request to change, fix, or add to the game.
---

# Change the game and ship it to the user's Mac

The user plays on a Mac (macOS 12.6). Their Desktop **Fright Feud** shortcut runs
`Launch Fright Feud.command`, which downloads the `main` branch from GitHub
(`scripts/mac-update.sh`), copies the game files into the installed game, and
relaunches the app. So **a change reaches the user only once it is on `main`.**
The user asked for changes to be merged into `main` automatically: do not open a
pull request and do not wait for review.

## 1. Make the change

- The game is `index.html` (questions are `ROUNDS` and `BONUS`; styles and logic
  are inline). Follow `CLAUDE.md`: relative asset URLs only, no CDNs, no build
  step, keep the host window, hidden answers, popup sender checks and the older
  Safari fullscreen fallback working.
- New game asset files go in `assets/` (the updater copies `index.html`,
  `app.json`, `fonts/` and `assets/` into the installed game). Anything elsewhere
  will not reach the installed game unless `GAME_ITEMS` in `scripts/mac-update.sh`
  is extended.

## 2. Test before shipping

1. Browser regressions (pass the bundled Chromium if the pip Playwright version
   does not match `/opt/pw-browsers`):
   ```sh
   python3 - <<'EOF'
   import runpy, glob, playwright.sync_api._generated as g
   exe = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))[-1]
   orig = g.BrowserType.launch
   g.BrowserType.launch = lambda self, *a, **k: orig(self, *a, **{"executable_path": exe, **k})
   runpy.run_path("tests/check_integration_seams.py", run_name="__main__")
   EOF
   ```
2. Exercise the changed controls in a real browser and look at fresh screenshots.
   Best: run App Engine (sibling `app-engine` checkout, `.venv` from its
   `requirements.txt`) with `APP_ENGINE_APPS_DIR` pointing at a scratch folder
   containing a `fright-feud` symlink to this repo, open
   `http://127.0.0.1:8770`, click Fright Feud. Use
   `--host-resolver-rules=MAP *.localhost 127.0.0.1` for Chromium. The splash
   covers the page for about 3.5 s; wait or press a key before clicking.
3. If App Engine source is available:
   `PYTHONPATH=../app-engine python3 -m app_engine.manifest .`
4. If Mac scripts changed: `bash -n` each one, and run them with a temporary
   `HOME` and stub `curl`/`open`/`osascript`/`mdfind` on `PATH`. Never touch real
   user directories. Do not stub `sleep` with a script that calls `sleep`.

## 3. Ship to main (no pull request)

```sh
BR="$(git branch --show-current)"
git add -A && git commit -m "<what changed for the player>"
git fetch origin main
git merge --no-edit origin/main         # resolve conflicts if any, re-test
git push -u origin "$BR"
git push origin "HEAD:main"             # fast-forward main to this commit
git ls-remote origin main               # must equal: git rev-parse HEAD
```

- If `git push origin HEAD:main` is rejected, fetch and merge again; never force-push
  `main`.
- Retry network failures up to 4 times with backoff (2s, 4s, 8s, 16s).
- Confirm GitHub serves the new commit (usually within a minute):
  `curl -fsSL https://codeload.github.com/yongk802/fright-fued/tar.gz/refs/heads/main | tar -xzO --wildcards '*/index.html' | grep -c '<something unique to the change>'`

## 4. Tell the user

Keep it short and concrete:
- what changed, and what was tested (and what was not, e.g. "not tried on a real Mac");
- **to see it: double-click Fright Feud on the Desktop** (it downloads the latest
  version and reopens the game). If the game tab is already open, the new tab is
  the updated one; close the old tab.
- Their own edits to installed `index.html`/`app.json` get replaced; the previous
  copy is in `~/Library/Application Support/Fright Feud/backups`.
