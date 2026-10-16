# Working on Fright Feud

This repository is a complete static App Engine app. Read README.md first.
The repository name is `fright-fued`; the app ID is `fright-feud`. Keep that ID
stable so App Engine installations continue to identify the same app.

- `index.html`: supplied game, questions (`ROUNDS` and `BONUS`), styles, and logic.
- `app.json`: portable engine manifest. No backend or build lifecycle is needed.
- `fonts/`: local fonts and original OFL licenses. Preserve notices.
- `scripts/package.py`: standard-library Python ZIP builder.
- `tests/check_integration_seams.py`: focused Playwright browser regressions.

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
