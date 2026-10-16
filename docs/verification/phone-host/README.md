# Phone host verification — 1.2.0

The delivered behavior is a private iPhone-sized host panel controlling the
contestant board served by real App Engine. No casting software or phone app is
required. The Mac's existing signed 1.1 app can use the feature through the
source-updating Desktop shortcut; a fresh 1.2 bundle includes it directly.

Product source was complete at `7cb3fb2` (including frontend recovery fix
`7458081`). Subsequent changes only extend verification and documentation.

## Final Mac archive

`Fright-Feud-macOS.zip`: 59,415,936 bytes.

SHA256: `d1129190bce223c5574e9c16c4064ccf39f1f96b0e5000d2705241060b7d72c6`.

The exact ZIP was extracted with ditto. Deep/strict code-sign verification passed;
all 20 content-addressed launcher/game payloads matched bundle.json. The builder
audited all 25 Mach-O files against macOS 12.6 and preserved the pinned engine,
runtime and dependency licenses. The app is ad-hoc signed, not notarized.

## Executed checks

* Focused Python suite: 167 passed, 15 compiled native subtests passed. The two
  tar extraction deprecation warnings concern the developer Python's future
  default and are not runtime failures.
* App Engine manifest: valid, engine 0.2.1.
* Original browser popup sender and prefixed Safari fullscreen regressions:
  passed.
* Exact extracted bundle: first install, installed-copy relaunch, repeat launch,
  stopped-engine restart, and full local gameplay passed on arm64 and x86_64.
  Intel ran through Rosetta on the build host.
* Exact extracted bundle: the same lifecycle plus two independent phone/board
  browser contexts passed separately on both architectures at the actual native
  launch URL. Phone width 390px; laptop 1440px. These checks include main game,
  bonus controls, hidden input and delayed points, timer pause/restore, masking,
  duplicate awards, stale rounds, held/queued save versus clear, rejected/lost
  draft recovery, phone and board refresh, lost heartbeats, superseding boards,
  and pairing-link revocation. Page errors and external requests were zero.
* Real already-running engine: missing game installation, edited game
  preservation, denied administration routes, and simultaneous clicks reusing
  one engine/helper passed on the final Intel bundle.
* Unmodified signed 1.1 bundle plus updated source entrypoint: started a new
  companion using its bundled Python and passed the real-engine phone browser
  flow in an isolated home. No signed bundle files were edited.
* Actual LAN IPv4 origin, separate phone browser context: synchronized round
  change and reveal passed. Engine administration returned 404; LAN access to
  board assets returned 403. Zero browser page errors/external requests.
* The generated QR screenshot decoded through macOS Vision to the exact pairing
  URL. No online QR service was used. At 1280×800 the contestant board fit in the
  viewport; use Full screen on the old laptop (a 720px-tall browser viewport can
  clip the bottom row).

The fresh screenshots alongside this file come from the exact final extracted
arm64 bundle and were inspected. Main/bonus host controls are readable at phone
width. The contestant screenshots show only revealed answers, scores and game
content; host controls and unrevealed bonus input are absent.

## Scope and investigation notes

Tests used disposable homes, explicit nonproduction engine ports, and
test-owned child processes. The real user's engine, installed game and settings
were not modified. No Atrium restart was required. Independent transport,
launcher, frontend specification/quality, and final integration reviews ended
Ready after fixing their reproduced findings.

An early legacy test waited for networkidle, which cannot occur with continuous
400ms polling; it now waits for the actual DOM and fonts. Two early qualification
attempts saw a transient helper connection refusal. No lifecycle defect could
be reproduced: an exact repeat passed, followed by three fresh-home monitored
cycles (three repeated native calls, full browser flow, twelve seconds extra
dwell each), with 331 paired health samples all 200. No production change was
made on an unconfirmed hypothesis. All four final extracted-bundle qualification
runs passed.

Physical iPhone Safari, macOS 12.6 hardware, downloaded-app Gatekeeper approval,
and graphical default-browser handoff were not directly tested. Native headless
mode exercises the same coordinator and validates its browser URL. The physical
devices may need normal incoming/local-network approval; the code never bypasses
security settings. HTTP pairing is intended for a trusted shared Wi-Fi network.

No configured run_tests/analyze_code environment was available for this
independent repository; verification used the exact checkout and supplied local
Python/Playwright environment. A Linux Claude web session can edit and run the
portable tests, but rebuilding the Cocoa bundle requires a Mac build host.
