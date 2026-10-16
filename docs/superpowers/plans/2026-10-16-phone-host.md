# Phone host implementation plan

Required executor: subagent-driven-development. Tracking: beads atrium-9wbyf;
this document describes implementation and is not a second task tracker.

Goal: pair an iPhone in Safari with a private touch host panel while the Mac
shows the synchronized contestant board.

Architecture: a standard-library LAN companion proxies only Fright Feud assets
from loopback App Engine. Authenticated snapshots and idempotent commands join
independent browser contexts. Existing Mac update and offline runtime are reused.

Tech: Python HTTP server, browser fetch polling, vanilla JavaScript/CSS, bundled
MIT QR generator, pytest and Playwright. Contract is in the adjacent approved
spec at `../specs/2026-10-16-phone-host-design.md`.

1. Transport: create `tests/test_phone_server.py` with real server fixtures and
   failing authenticated claim/sync/command tests. Run with `.venv/bin/python -m
   pytest tests/test_phone_server.py`. Implement `desktop/phone_server.py` for
   the exact endpoints, bounds, heartbeat, lease, deduplication and proxy limits.
   Add denial tests for engine routes, LAN board access, redirects, foreign
   Origin/Host and oversized/invalid commands. Re-run, inspect diff, commit only
   those files. Obtain independent spec and quality reviews.

2. Game adapter and phone: write `tests/check_phone_host.py` using two independent
   Playwright contexts against the real helper and a test engine. First assert
   Connect phone exists (fails before implementation). Create
   `assets/phone-board.js`, `assets/phone-host.html`, `assets/phone-host.js`,
   `assets/phone-host.css`; load the board adapter at the end of `index.html`.
   Expose no private UI on paired laptop. Serialize/restore the exact spec state,
   process allowlisted commands, ACK applied IDs, and poll at 400ms with a single
   in-flight request. Preserve pending input focus and disable disconnected
   controls. Test setup, standard and bonus actions, phone refresh, board refresh
   and supersession. Inspect both screenshots and run original browser seams.
   Commit focused files, obtain spec review and quality review.

3. Launch/update integration: add `scripts/launch_phone.py` using bundled Python
   and native headless NDJSON, durable helper copy, nonce health checks and flock;
   update the Desktop command to run it on installed app path and retain normal
   first-open path. Extend `desktop/launcher.py` to use the companion on new
   bundles without changing the loopback relay contract. Update native URL
   validator for the exact ff_board fragment. Add failing focused launcher and
   bundle tests before edits. Include assets/helper in `copy_payload` and static
   package. Run focused Python/shell tests, then actual test-only engine launch.

4. Delivery: update README/CLAUDE and distribution instructions for same Wi-Fi,
   firewall approval, private pairing link, offline availability and reconnect.
   Build static ZIP and universal Mac ZIP, verify signatures and archive payload,
   and exercise the extracted bundle on both supported binary architectures.
   Run combined relevant tests and independent final review, repair findings,
   then commit/push main and publish a versioned release. Confirm remote commit
   and uploaded digest. Close beads only after evidence is saved.
