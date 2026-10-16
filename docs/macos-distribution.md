# Mac distribution

`dist/Fright-Feud-macOS.zip` contains **Fright Feud.app**. The Mac app bundles the
game, App Engine, Python 3.12, and all Python dependencies for Intel and Apple
Silicon. No package manager, Python installation, Git checkout, developer tools,
or setup network access is required on the target Mac.

The ordinary `dist/fright-feud-app-engine.zip` remains available for users who
want only the static game for an existing engine.

## First and later launch

Open the Mac app in Finder. It installs an owned launcher under `~/Applications`,
serializes concurrent launches, and checks for a compatible local engine. A
running engine with the game is reused. If the game is missing, it is installed
into an engine-owned writable app root and its catalog is refreshed. Otherwise
the included engine is started with loopback binding and durable per-user state.
Occupied ports are checked by engine identity; unrelated listeners are left alone.

The game opens directly at a numeric `127.0.0.1` address in the default browser.
An app-scoped loopback relay fetches only Fright Feud assets from the engine's
isolated app origin. This handles [older Safari's localhost-subdomain issue](https://bugs.webkit.org/show_bug.cgi?id=160504)
without DNS/hosts-file edits. The relay uses a separate port/origin and cannot
forward engine controls, other apps, or external redirects. The game is still
served by App Engine. Reopening the launcher
uses the existing game and engine; the launcher does not overwrite edited game
files. Versioned resource copies allow the downloaded ZIP/folder to be removed
after installation without breaking subsequent launches.

The native progress window exits after opening the game. The engine runs in the
background for later opens, without a login startup job. Game state is in browser
memory and resets on reload, as before. Files and logs for the launcher's own
installation live under `~/Library/Application Support/Fright Feud`.

## macOS compatibility and first-open approval

The native launcher targets macOS 12.0. Its portable Python builds target macOS
11.0 on Apple Silicon and 10.15 on Intel. Bundled dependency binaries must also
pass a deployment-target audit before a release is published. Both architecture
paths are exercised on the build host when Intel translation is available.
These checks do not constitute a physical test on macOS 12.6 hardware.

The app is ad-hoc signed so resource integrity can be checked. A Developer ID
certificate and Apple notarization service are not configured for this project.
Consequently a downloaded copy may need the normal Finder first-open approval.
On macOS 12.6, Control-click the app, choose Open, and follow the operating
system's approval dialog. No installer code disables Gatekeeper, strips
quarantine, changes certificate trust, or removes security protections.

## Build and verify (developer machine only)

The public repository contains the complete launcher and build source. Building
the Mac distribution requires macOS with Xcode command-line tools, Python 3.12+,
`uv`, and an App Engine Git checkout containing the pinned commit in the lock.
The build machine downloads and verifies the locked Python runtime artifacts and
resolves only the hash-pinned Python wheels; the resulting app works offline.

`desktop/runtime-lock.json` records runtime URLs/digests and the clean App Engine
source commit. `desktop/requirements-macos.lock` pins Python dependencies.
`scripts/build_macos.py --help` describes build arguments. The builder excludes
uncommitted changes from the engine checkout. Engine source licenses, Python
licenses, and package distribution notices are kept in the app bundle.

The native executable supports headless qualification so tests can verify install
and relaunch behavior without opening a real user browser. Tests must always use
an explicit temporary home and a nonproduction loopback port. For a built app:

```sh
python3 tests/check_macos_distribution.py --bundle '.build/macos/Fright Feud.app' --arch arm64
python3 tests/check_macos_distribution.py --bundle '.build/macos/Fright Feud.app' --arch x86_64
```

The x86_64 test on Apple Silicon requires translation support on the developer
machine. Playwright belongs only in that development environment. It is not
included as a runtime dependency. Tests exercise the real bundled engine and game
and save fresh browser screenshots; they also test native first/repeated launch
and stopped-engine restart using isolated directories with spaces.

`python3 tests/check_existing_engine.py --bundle '/path/to/Fright Feud.app'`
additionally verifies installing into an already-running real engine, preserving
locally edited game files, denying engine-control routes on the numeric relay,
and serializing concurrent native clicks into one engine and relay.

## Work through Claude Code on the web

Select this GitHub repository in Claude Code on the web. The cloud session can
edit the game and launcher source and run platform-independent Python tests.
A Linux cloud environment cannot build or execute the Cocoa Mac app; use a Mac
build machine for the universal binary and complete release qualification.

After reviewing and merging changes, download an updated Mac release to install
them, or copy updated game files into the game folder of your active App Engine.
The launcher preserves existing game source, so edited installations are not
silently replaced by a newer bundle. A GitHub cloud session has no direct access
to your local running game or files unless you separately connect such access.
