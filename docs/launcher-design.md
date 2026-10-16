# One-click Mac distribution

The user explicitly requested packaging App Engine with Fright Feud: install the
engine/game when missing and otherwise launch the installed game. Their target
is macOS 12.6. This extends the earlier static ZIP into a complete Mac app.

## User behavior

Unzip and open `Fright Feud.app`. Its native progress window installs an owned
copy in `~/Applications/Fright Feud.app` if needed and opens the engine-hosted game
in the default browser. Reopening the app reuses the installed game and running
engine. Existing game folders are preserved rather than overwritten. First-open
Gatekeeper approval may be required because no Developer ID notarization identity
is available. No security settings are changed or quarantine attributes removed.

## Components and interfaces

- `desktop/launcher.py`: standard-library install/lifecycle coordinator.
  `launch(resources: Path, home: Path, preferred_port: int) -> dict` returns
  `{url: str, reused_engine: bool, installed_game: bool, pid: int | null}`.
  It emits JSON status lines and a final result. Failure is a nonzero exit with
  an actionable error. Command-line test overrides use explicit temporary paths.
- `desktop/FrightFeud.swift`: universal Cocoa launcher targeting macOS 12.0. It
  selects the bundled Intel/ARM Python, runs the coordinator asynchronously,
  displays progress/errors, and opens only a validated loopback game URL.
- `scripts/build_macos.py`: reproducible builder. Bundles a pinned clean App
  Engine Git snapshot, both checksum-verified portable Python distributions,
  pinned binary dependencies, source licenses, the game, and native launcher.
  Output `dist/Fright-Feud-macOS.zip` contains one `Fright Feud.app`.

Resources layout: `launcher.py`, `bundle.json`, `engine/` (complete engine source
and its required frontend/assets), `game/` (app.json/index.html/fonts), and
`runtimes/{arm64,x86_64}/python/`. Each Python runtime includes its dependencies.
`bundle.json` identifies app/engine/runtime versions and engine source commit.

The coordinator serializes installation with a per-user file lock. It probes
configured/default local engine ports using `/api/engine`; it never terminates
an existing service or assumes an occupied port is App Engine. A running engine
with the game is reused directly. A running engine without it receives a new
app folder in a writable root, followed by catalog refresh through its normal
API. If no suitable engine runs, the coordinator starts the bundled engine with
loopback binding, isolated durable state, a stable remembered port, and log file.
Fallback ports avoid unrelated listeners. Existing game data/source is preserved.

The launcher owns only its support directory and bundle ID
`com.yongk802.fright-feud`. Same-name unrelated apps/folders cause a clear error.
Versioned runtime resources prevent overwriting a running engine during updates.
The native launcher exits after opening the browser; the engine stays available
until logout or normal process termination, with no login autostart.

## Qualification

Tests must first fail for missing launcher behavior. Cover fresh installation,
repeat launch, stopped-engine restart, existing-engine game install/reuse, port
collision, unrelated folders, concurrent clicks, corrupt/partial installations,
and paths with spaces. Run real bundled ARM and Intel Python where this host
supports execution. Audit Mach-O deployment targets at or below macOS 12.6.
Verify native bundle signing, ZIP executable bits/symlinks, launcher URL safety,
and game interaction/screenshots through the actual bundled engine. No claim of
testing on physical macOS 12.6 hardware is implied by binary compatibility checks.
