# Separate phone pairing window — 1.2.3

Connect phone now opens a dedicated local page in its own 520 × 760 browser
window. No pairing overlay is inserted into the game. Repeated clicks focus and
refresh the owned window; closing it leaves the board running. An already-paired
phone does not prevent reopening the window. Popup-blocker guidance persists
until opening succeeds, including while a phone is connected.

The pairing window closes on first connection, acknowledged phone disconnect,
parent page exit, or replacement of the board lease. Disconnect therefore cannot
leave a revoked QR code visible. The manual host link opens separately with
noopener/noreferrer. A local ready message is accepted only from the owned window
and exact origin. No board capability appears in the child URL. Its fonts,
palette and offline QR implementation are retained.

A dedicated HTML/CSS/JS page avoids a verified about:blank/document.write resource
loading failure under browser request interception. The final local fonts and
QR display were visually judged from fresh packaged-app screenshots.

Verification:

- Old overlay implementation failed the new-window expectation before the change.
- A paired-state blocked-popup regression failed before the lifecycle correction.
- Full paired-browser regression passed, including reuse, close/reopen, blocker
  hints before/after pairing, QR generation, disconnect cleanup, scoring, private
  bonus entry, timers, reconnection and lease replacement. No page errors or
  external requests. An independent read-only reviewer also ran it successfully.
- Extracted final universal Mac bundle passed arm64 paired-phone and x86_64
  local-game/host-popup workflows through real disposable App Engine instances,
  with installation, repeated launch and engine restart checks.
- Integration sender/fullscreen checks passed. Bundle checks: 14 tests plus 15
  subtests passed. Offline build audited 25 Mach-O deployment targets; strict
  deep signature and payload hashes were verified.

The existing local Mac launcher from 1.2.2 can use these updated game assets
without changing its signed bundle. Physical iPhone and macOS 12.6 Safari were
not directly tested; browser settings can determine whether a separate page is
shown as a window or a tab.
