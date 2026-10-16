# One-click Mac launcher implementation plan

Goal: deliver an offline-capable Mac app bundling App Engine and the game.
Architecture and public interfaces are in launcher-design.md. Track progress in
beads `atrium-ghk5u`; do not use Markdown task lists for task tracking.

1. Implement and test the Python coordinator in `desktop/launcher.py` and
   `tests/test_desktop_launcher.py`, beginning with failing tests. Own only those
   files. Use HTTP engine identity/catalog contracts, safe game install, lock,
   durable bundle/runtime copies, process reuse, logging, and bounded readiness.
2. Implement native Cocoa launcher and reproducible universal Mac builder in
   `desktop/FrightFeud.swift`, `scripts/build_macos.py`, and resource lock files.
   Target macOS12, ship Intel+ARM Python with binary dependencies, verify
   checksums/minimum OS, preserve license notices, and ad-hoc sign the app.
3. Integrate against the fixed resource/JSON contracts, run focused tests, build
   and extract the final ZIP, test fresh/repeated install using an isolated home,
   and run browser game tests through the bundled engine. Inspect fresh screenshots.
4. Independent read-only review, repair blocking findings, then update README and
   Claude instructions. Publish a new GitHub release with the complete Mac ZIP,
   retain the static App Engine ZIP separately, push all owned changes and close
   beads. Preserve unrelated Atrium/App Engine checkout changes.

Self-review: the plan covers the user's exact installation/relaunch request and
macOS12.6 constraint; there is no user-side Python/git/Terminal dependency.
Existing host security settings and unrelated services remain intact.
