# Fright Feud 🎃

A Halloween survey party game for **App Engine**, with four selectable games. Each has three main rounds (single, double, and triple points),
team scores and strikes, keyboard buzzers, synthesized sound effects, a printable
answer key, and five Fast Fright bonus questions with private host controls.
Finish each game in the bonus round to save its team scores, winner, and bonus total.
The next unplayed game is selected automatically; replaying a game replaces its result.
Game selection and results are available on the laptop and paired phone.
Results use browser storage; the Mac phone companion also saves them privately
under `~/Library/Application Support/Fright Feud/game-results.json`, surviving relaunches.
A disk warning leaves the game playable; keep the board open until saving succeeds.

All game code and fonts are included. There is no npm install, compilation,
AI model, account, or internet connection needed to play.

## One-click Mac app — App Engine included

Download **[Fright-Feud-macOS.zip](https://github.com/yongk802/fright-fued/releases/download/v1.2.3/Fright-Feud-macOS.zip)**,
unzip it in Finder, and open **Fright Feud.app**. It supports Intel and Apple
Silicon Macs running macOS 12.6 or later. Python, App Engine, their dependencies,
and the game are bundled, so the target Mac needs no developer tools or setup
downloads.

On first open, the launcher installs its owned copy under
`~/Applications/Fright Feud.app`. It reuses a compatible local App Engine when
available and installs Fright Feud into that engine if the game is missing.
Otherwise it starts the included engine. The game opens directly in your default
browser. On later opens, it reuses the installation and running engine. Existing
game files are preserved. It never stops unrelated services or enables login
autostart.

macOS may require its normal first-open approval for a downloaded app. This build
is ad-hoc signed, not Developer ID notarized; it does not bypass Gatekeeper or
change security settings. If approval is needed on macOS 12.6, use Finder's
normal **Control-click → Open** flow. Component installation is automatic after
the operating system allows the app to open.

The launcher displays progress and explains startup errors. Its own engine state
and logs live under `~/Library/Application Support/Fright Feud`. You can remove
the downloaded copy after the installed app has opened successfully. Close the
browser when finished; the local engine stays available for the next launch.

See [Mac distribution details](docs/macos-distribution.md) for development,
verification, and the distinction between the full Mac app and the static ZIP.

## Desktop shortcut that always plays the latest version (Mac)

After Fright Feud.app has opened once, paste this into Terminal:

```sh
curl -fsSL https://raw.githubusercontent.com/yongk802/fright-fued/main/scripts/mac-desktop-setup.sh | bash
```

It creates a **fright-fued** folder with every project file and a **Fright Feud**
shortcut with a pumpkin icon on the Desktop. Each time you double-click
the shortcut, it downloads the latest `main` branch from GitHub, updates the
installed game, and opens it in a new browser tab. Without internet, it opens the
version already installed. Earlier copies are kept under
`~/Library/Application Support/Fright Feud/backups`.

**Get Latest Updates.command** in the folder updates without launching. The icon
is in `icon/` if you want to assign it elsewhere.

## Static ZIP for an existing App Engine

`fright-feud-app-engine.zip` is the smaller, platform-independent app package.
It requires an existing App Engine and is separate from the complete Mac bundle.

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

### Use your iPhone as the host

1. Connect the Mac and iPhone to the same Wi-Fi. Open Fright Feud using the
   Desktop shortcut (which gets the latest source), or a fresh version 1.2 Mac install.
   When upgrading the older Desktop shortcut for the first time, let it update,
   close that game tab, and launch the shortcut once more so it uses the new launcher.
2. Click **Connect phone** on the laptop to open the separate pairing window,
   then scan its QR code with the iPhone Camera and open it in Safari. A link is
   also provided for manual entry. If the browser blocks the window, allow
   pop-ups for the local game and click **Connect phone** again.
3. The phone shows private answers and touch controls. Enter team names there,
   start the game, and use the phone for reveals, scores, strikes and rounds.
   The laptop automatically hides the host controls and closes the pairing window
   once paired. **Connect phone** can reopen it without covering the board.
4. For Fast Fright, enter answers and points on the phone, then tap **Reveal**
   when ready. Unrevealed input stays off the contestant board.

Keep Safari open on the phone and keep the Mac awake during play. After a brief
Wi-Fi interruption or phone refresh, the phone reconnects to the current game.
Reloading the paired laptop restores the most recent in-memory snapshot with
the timer paused. Restarting the Mac or ending the companion clears that session.

If macOS asks to allow incoming network connections for the bundled Python,
allow it on your trusted network. Allow Safari local-network access if asked.
Guest Wi-Fi that isolates devices cannot pair;
use a network that allows the devices to communicate. Internet is not needed
for pairing or play. Keep the private QR/link for the host: anyone who has it on
that network can control the game. **Disconnect phone** revokes that link.
The helper exposes game messages only, never App Engine's administration.

An older installed Mac app gains this feature through the updated Desktop
shortcut without changing its signed app bundle. If Connect phone says the
companion is unavailable, close the game and launch the Desktop shortcut again.
The static App Engine package retains local/popup play; cross-device hosting
also requires the companion service from the Mac distribution or source.

### Play locally

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

Game state is held in memory. In local/popup play, reloading resets it. Paired
play keeps its most recent snapshot in the companion until that service exits.
Changing rounds clears that round's board but retains team scores.
Survey points are made up for party play, not actual survey results.

## Develop with Claude Code on the web (no local Claude installation)

1. Open <https://claude.ai/code> in your browser and connect GitHub. Give Claude
   access to <https://github.com/yongk802/fright-fued> and select that repository.
2. Describe the change. For example: “Add five Halloween questions. Preserve the
   App Engine manifest and offline operation. Read CLAUDE.md and rebuild the ZIP.”
3. Ask Claude to test the change and push it to `main`, following this repository's
   `update-game` skill. The Desktop shortcut downloads that branch.
4. Double-click **Fright Feud** on the Mac Desktop to update and launch. Close the
   old game tab and start a new game after updating. No local Claude CLI needed.

Claude works on a **cloud copy of the GitHub repository**. Installing the app on
your Mac does not connect Claude to your files or running App Engine. Unpushed
local edits are invisible to it; launching your Desktop shortcut brings its
published changes to your Mac. Share screenshots and reproduction steps when a problem only happens
on your older browser. Web access depends on your Claude plan and organization.

Official references: [Claude Code cloud/web workflow](https://code.claude.com/docs/en/claude-code-on-the-web)
and [local system requirements](https://code.claude.com/docs/en/setup). The local
CLI currently requires macOS 13+; browser-based cloud coding avoids that install.
The game uses older-Safari-compatible web APIs, but macOS 12.6 hardware has not
been directly tested as part of this packaging work.

## Edit and rebuild

`index.html` contains the app's HTML, styles, questions, and game code. Edit
`GAMES` for the four sets of main-round and bonus questions. Keep up to
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
