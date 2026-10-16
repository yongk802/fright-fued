# Layout polish — 1.2.1

The requested pass preserves every original font and color. It changes layout,
spacing, control sizing, safe-area padding, and wrapping only. The phone timer
controls receive one presentational class; game data and command logic are unchanged.

## Judged browser evidence

Screenshots were captured from a disposable real App Engine with the app-only
phone companion, using independent contestant and private-host browser contexts.
The screenshots in this directory were visually judged after capture.

- `board-640.png`: complete contestant board with browser-toolbar-sized viewport.
- `board-720.png`: complete contestant board at 1280 × 720.
- `phone-main-390.png`: aligned team controls, score entry, and answer buttons.
- `phone-bonus-viewport-320.png`: timer buttons remain usable on a narrow phone.
- `local-game-390.png`: local game controls use equal columns and matched heights.
- `phone-keyboard.png`: focused answer entry in a 375 × 380 viewport.

All eight rounds fit at 1280px width and viewport heights 640, 680, 720, and 800.
The lowest board edge was 624.2px at heights 640/680, 686.6px at 720, and 715.4px
at 800. Phone main layouts were checked at widths 320, 375, 390, 430 and landscape
844; bonus entry at 320, 375 and 390. No horizontal overflow or phone buttons below
44px height were observed. Narrow team cards stack below 380px.

A before/after comparison checked computed font family, size, weight, style,
letter spacing and line height, plus text/background/border colors, gradients and
shadows for 1,801 matching elements across 11 board/phone snapshots: zero changes.
The original inline game CSS, font files, font declarations, and color values
remain unchanged in the source diff.

## Regression and distribution checks

- Paired phone gameplay against real App Engine: pass, including main scoring,
  private bonus entries, reveals, timers, reconnection and stale commands.
- Local gameplay and separate host window through App Engine: pass; no page
  errors or external requests. Popup sender/fullscreen fallback checks: pass.
- Independent specification and code reviews: no blocking findings. Independent
  phone transport/launch/entrypoint checks: 98 passed.
- Bundle builder checks: 14 tests plus 15 subtests passed.
- Extracted final Mac ZIP tested through both x86_64 (Rosetta) and arm64 launcher
  paths: first install, repeated launch, installed app, engine restart and full
  paired-host/local gameplay checks passed.
- Offline build: 25 bundled Mach-O files passed the macOS 12.6 minimum-version
  audit. Extracted app passed strict deep code-sign verification. All 21 payload
  hashes match; the layout asset matches the reviewed source.

The bundle is ad-hoc signed, not notarized. Browser checks used Chromium on the
current development Mac. A physical iPhone, its actual onscreen keyboard, and
macOS 12.6 Safari were not available; reduced-height emulation is not a physical
keyboard test. Configured `run_tests` / `analyze_code` tools were unavailable, so
focused repository checks were run directly in the development Python environment.
