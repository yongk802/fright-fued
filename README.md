# Fright Feud 🎃

A Halloween survey party game for **App Engine**, with eight main rounds,
team scores and strikes, keyboard buzzers, synthesized sound effects, a printable
answer key, and a five-question Fast Fright bonus round with private host controls.

This is a complete static app: all game code and fonts are included. There is no
npm install, compilation, AI model, account, or internet connection needed to play.
**App Engine must already be installed and running.** This ZIP is an app package,
not an installer for App Engine or a double-click executable.

## Install the ZIP in App Engine

1. Unzip `fright-feud-app-engine.zip`. On macOS, double-click it in Finder.
2. Find the extracted folder containing **both `app.json` and `index.html`**.
   Rename that folder **`fright-feud`**. Do not select its `fonts` or `scripts` folder.
3. Move the folder inside the apps directory your App Engine uses. The final layout
   must be `YOUR_APPS_DIRECTORY/fright-feud/app.json` and
   `YOUR_APPS_DIRECTORY/fright-feud/index.html`.
4. Refresh the App Engine launcher, then select **🎃 Fright Feud**. If it isn't
   listed, use **App Studio → Apps → Refresh**, then reload the launcher.

Your apps directory is the engine's `APP_ENGINE_APPS_DIR` setting. If your setup
uses the `personal-apps` collection, place `fright-feud` alongside its other apps.
App Studio's **Import → Inspect project** checks a directory; it does not upload
ZIPs or move an arbitrary folder into the catalog. The folder must be under an
engine scan root to appear in the launcher.

To use this Git checkout directly, its containing directory can be an apps scan
root. The manifest ID stays **`fright-feud`** even though the GitHub repository is
spelled **`fright-fued`**. Use one installed copy at a time so an older copy doesn't
take precedence in the engine catalog.

## Play

Enter the two team names and choose **Start the game**. Reveal answers by clicking
tiles or pressing **1–8**. Use **Q/P** for buzzers, **B** to reset buzzers, **X** for
a strike on the active team, and arrow keys to change rounds. Award the pot to a
team before moving to the next round. Scores can also be edited with **Edit score**.

Use **Bonus round → Open host controls** to open a second window. Allow pop-ups
for the App Engine game site if your browser asks. Keep that window on the host's
screen and show the game window on the TV. Answer text stays hidden from the
audience until **Reveal**; points appear a moment later. The host window includes
20/25-second timers, survey-answer shortcuts, player-one masking, and a total.
**Host answer key** opens a separate printable window.

The app's **Full screen** control supports the standard and older Safari APIs.
If the browser disallows it inside a frame, use the browser's full-screen control.
The app declares the sandbox permissions needed for the host window and score
dialogs, plus fullscreen permission. Use App Engine's normal isolated app origins.

Game state is held in memory, as in the original game. **Reloading or closing the
game resets it.** Changing rounds clears that round's board but retains team scores.
Survey points are made up for party play, not actual survey results.

## Develop with Claude Code on the web (no local Claude installation)

1. Open <https://claude.ai/code> in your browser and connect GitHub. Give Claude
   access to <https://github.com/yongk802/fright-fued> and select that repository.
2. Describe the change. For example: “Add five Halloween questions. Preserve the
   App Engine manifest and offline operation. Read CLAUDE.md and rebuild the ZIP.”
3. Review Claude's diff and pull request, then merge the changes you want.
4. On the old Mac, download the updated repository using GitHub's **Code → Download
   ZIP**, or run `git pull --ff-only` from your local checkout if you use Git.
5. Replace the installed app's files with the updated files, or update the checkout
   directly if App Engine scans it. Keep `app.json` and `index.html` together at the
   app root. Close/reopen the game or reload its frame; refresh the catalog if the
   manifest changed. Start a new game after updating.

Claude works on a **cloud copy of the GitHub repository**. Installing the app on
your Mac does not connect Claude to your files or running App Engine. Unpushed
local edits are invisible to it, and its changes do not automatically appear on
your Mac. Share screenshots and reproduction steps when a problem only happens
on your older browser. Web access depends on your Claude plan and organization.

Official references: [Claude Code cloud/web workflow](https://code.claude.com/docs/en/claude-code-on-the-web)
and [local system requirements](https://code.claude.com/docs/en/setup). The local
CLI currently requires macOS 13+; browser-based cloud coding avoids that install.
The game uses older-Safari-compatible web APIs, but macOS 12.6 hardware has not
been directly tested as part of this packaging work.

## Edit and rebuild

`index.html` contains the app's HTML, styles, questions, and game code. Edit
`ROUNDS` for the main questions and `BONUS` for the bonus questions. Keep up to
eight answers per main question and five bonus questions.

Rebuild the distribution using **Python 3.9+** (no packages required):

```sh
python3 scripts/package.py
```

Output: `dist/fright-feud-app-engine.zip`, with `app.json` at its root. Python is
needed only to rebuild the ZIP, not to play this static app in an existing engine.
If your older Mac lacks a suitable Python, ask Claude's cloud session to run this
command and attach the resulting ZIP, or use **Download ZIP** from GitHub and
install that extracted source folder directly. `dist/` is excluded from Git.

Optional development verification (in a cloud/dev environment with Playwright):

```sh
python3 -m pip install playwright
python3 -m playwright install chromium
python3 tests/check_integration_seams.py
```

The browser test checks popup sender isolation and the older Safari fullscreen
fallback. Full release checks additionally launch the packaged game through a
real App Engine and exercise scoring, bonus controls, popups, and offline assets.
With a disposable engine already serving this app, run
`python3 tests/check_app_engine.py --url http://127.0.0.1:19937` for those checks.
It blocks external browser requests and saves screenshots under `test-results/`.

## Font notices

Creepster and Oswald are bundled under the SIL Open Font License 1.1. Their
licenses are in `fonts/`. See `THIRD-PARTY-NOTICES.md` for sources. The supplied
game retains its existing ownership; this package does not assign it a new license.
