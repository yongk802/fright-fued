# Working on Fright Feud

This repository is a complete static App Engine app. Read README.md first.
The repository name is `fright-fued`; the app ID is `fright-feud`. Keep that ID
stable so App Engine installations continue to identify the same app.

- `index.html`: supplied game, questions (`ROUNDS` and `BONUS`), styles, and logic.
- `app.json`: portable engine manifest. No backend or build lifecycle is needed.
- `fonts/`: local fonts and original OFL licenses. Preserve notices.
- `scripts/package.py`: standard-library Python ZIP builder.
- `tests/check_integration_seams.py`: focused Playwright browser regressions.
- `desktop/`: the macOS install/lifecycle coordinator, Cocoa launcher, and locked
  dependencies for the complete offline distribution.
- `desktop/relay.py`: app-only numeric-loopback transport for older Safari;
  preserve its separate origin and strict route/Host/method limits. Never expose
  engine controls or other apps through it.
- `scripts/build_macos.py`: builds `dist/Fright-Feud-macOS.zip`, containing a
  universal `Fright Feud.app` with Python, App Engine, and the game bundled.
- `tests/test_desktop_launcher.py` and `tests/test_macos_bundle.py`: launcher and
  builder behavior checks. `tests/check_macos_distribution.py` qualifies a built
  or ZIP-extracted Mac app through both architecture paths and the real engine.

Preserve offline play: use relative asset URLs and bundle dependencies. Do not add
CDN imports or npm/build requirements without an explicit request. Preserve the
separate host window, audience-hidden answers, popup sender checks, and older
Safari fullscreen fallback. Host windows communicate only with the actual opener
through postMessage. Fullscreen failure must be handled without an unhandled error.

The user's target Mac runs macOS 12.6. Do cloud development in Claude Code on the
web; do not require them to install the Claude CLI. Their local installation does
not auto-sync with this repository. Explain how to download/pull and reload each
update. State any browser/version limitations honestly.

Run focused browser checks when changing integration behavior:

```sh
python3 tests/check_integration_seams.py
```

Install Playwright in the development environment if needed; it is not a runtime
dependency. For gameplay changes, exercise the affected controls in the browser,
including the host window when relevant, and inspect fresh screenshots. When
App Engine source is available, validate using
`python3 -m app_engine.manifest .` with that source on PYTHONPATH. No claim of
App Engine validation is justified by a plain static-server preview alone.

Before delivery, run `python3 scripts/package.py` and provide the resulting
`dist/fright-feud-app-engine.zip` if the environment supports downloadable outputs.
The ZIP must have `app.json` and `index.html` at the root. Do not include `.git`,
virtual environments, credentials, caches, or test screenshots. Commit changes to
the user's chosen branch and use a pull request for review when appropriate.
Do not add AI co-author trailers unless the user asks for them.

For the user's one-click Mac installation request, the primary deliverable is
**Fright-Feud-macOS.zip**, not the smaller static ZIP. It must install missing
engine/game components and otherwise launch the existing game directly. Build
with `python3 scripts/build_macos.py --engine-repo /path/to/app-engine` on macOS
with Xcode CLI and uv. Use the pinned clean engine commit, checksum-verified
runtimes, hash-pinned wheels, preserved licenses, minimum-OS audit, and code-sign
verification. No target-Mac downloads or developer tools are allowed. A Linux
Claude web environment can edit/test the Python source but cannot build Cocoa.

Test using temporary homes and explicit nonproduction ports. Never stop the real
user's engine, touch Atrium, or write test apps into the real user's app roots.
Preserve edited installed game files and unrelated ports/directories. Keep first
open Gatekeeper approval explicit: do not bypass quarantine/security checks or
claim notarization without an actual Developer ID/notarized build.
