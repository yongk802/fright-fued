# Paired phone host

The user approved an iPhone host with private answers and controls, with the
MacBook showing the contestant board. The prior recommendation (same-Wi-Fi QR
pairing in Safari, no phone installation) and the user's confirmation authorize
this design and implementation.

Use an app-scoped Python standard-library companion alongside the existing
App Engine. Screen streaming would require third-party display software and
offer poor touch controls; an internet-hosted session adds an unnecessary online
dependency. A LAN companion works offline after launch and preserves the current
game engine, browser sounds, and bonus window fallback.

The Mac remains the authoritative game. A locally served board publishes its
complete private snapshot and consumes validated commands. The phone polls the
snapshot and submits actions. Unrevealed answers and bonus input appear on the
phone only. Pairing automatically hides laptop host/navigation controls and
closes the QR panel; local fullscreen and reconnect controls remain available.
The local standalone/popup workflow remains available when no phone is paired.

## Transport contract

`make_server(engine_port: int, listen_port: int = 0, nonce: str)` returns a
`ThreadingHTTPServer` bound to IPv4 LAN, and proxies only the fixed Fright Feud
asset prefix to loopback App Engine. The board URL is
`http://127.0.0.1:PORT/apps/fright-feud/#ff_board=NONCE`. Engine administration,
other apps, absolute URLs, redirects, traversal, and forwarded credentials are
never exposed. The existing strictly local relay remains unchanged.

All API responses are JSON, no-store, no CORS. Host is restricted to loopback or
actual private/link-local local interface addresses, with the service port.
Requests with a foreign Origin are denied. Body size, command queue, IDs and
action payloads have explicit bounds. Pairing is a random bearer token in the
URL fragment, used by same-origin requests. No tokens in request URLs or logs.
HTTP on trusted Wi-Fi is sufficient for this party game; no claim of TLS.

Board-only endpoints require loopback peer and `Authorization: Bearer NONCE`:

* GET `/phone/health`: `{name:'fright-feud-phone', engine_port, nonce, version:1}`.
* GET `/phone/info`: `{host_urls:[string], host_token:string, host_connected:boolean}`.
  URLs include `/phone/#TOKEN`; use actual private interface IPv4 addresses and
  provide instructions if no usable network exists.
* POST `/phone/claim` `{}`: `{lease:string,state:object|null}`. A new board lease
  invalidates previous boards, clears pending commands, and returns the last
  snapshot for refresh recovery.
* POST `/phone/sync` `{lease:string,state:object,ack:[string]}`:
  `{commands:[{id:string,action:string,args:object}],host_connected:boolean}`.
  Retain commands until ack; expire commands after ten seconds. Reject invalid
  leases with 409. Update board heartbeat on sync.

Phone endpoints use `Authorization: Bearer HOST_TOKEN`:

* GET `/phone/state`: `{state:object|null,board_connected:boolean}`; updates phone
  heartbeat. Board considered disconnected after five seconds.
* POST `/phone/command` `{id:string,action:string,args:object}`: `{accepted:true}`.
  Deduplicate repeated IDs, reject disconnected boards with 409, invalid input
  with 400, unauthenticated with 403, bounded queue exhaustion with 429.

Public routes are only GET/HEAD `/phone/`, `/phone/host.js`, `/phone/host.css`.
They map to fixed game assets. The main game asset prefix is loopback-only.
The phone never receives the engine's session/control token.

## State and actions

Snapshot version 1 is `{version:1, screen:'setup'|'game'|'bonus', main:{teams:
[{name,score,strikes}],r,revealed:[int],pot,awarded,active,buzz,multOverride,showQ},
bonus:{rows:[[{text,pts,shown,ptsShown}]],mask,left,running},rounds:ROUNDS,
questions:BONUS,soundOn:boolean}`. It excludes timer handles and audio objects.
Browser reload restores the last snapshot, with the timer paused explicitly.
Phone reload polls the same current game. A second board supersedes the old one.

Allowed actions: `start` `{names:[string,string]}`, `screen` `{screen}`, `reveal`
`{i,round}`, `revealRemaining` `{round}`, `round` `{i}`, `strike` `{team}`, `unstrike`
`{team}`, `active` `{team}`, `award` `{team,round}`, `score` `{team,score}`, `buzz`
`{team}`, `resetBuzz` `{}`, `question` `{}`, `multiplier` `{}`, `sound` `{}`,
`bonusSet` `{p,i,text,pts}`, `bonusReveal` `{p,i}`, `bonusHide` `{p,i}`,
`bonusRevealAll` `{p}`, `timer` `{seconds:20|25}`, `timerStop` `{}`, `bonusMask` `{}`,
`bonusReset` `{}`, `duplicateBuzz` `{}`, `disconnect` `{}`. Unknown or out-of-range
commands are rejected by both boundaries. Round-sensitive actions cannot reveal
or award a different round after navigation. Clear/reset and disconnect require
phone confirmation. No arbitrary selectors, JavaScript, URLs, or file operations.

Phone UI uses large touch targets, readable responsive layout, live status and
disabled controls on disconnection. It preserves active text input while polling.
The laptop hides answer controls after pairing; only revealed answer faces remain
visible. QR generation is bundled and licensed, with no external service.

## Launch and delivery

Existing Desktop launch shortcut updates main, then invokes the existing signed
native app in headless mode using its bundled Python, starts/reuses the new
companion, and opens the board URL. No system Python dependency, signed bundle
mutation, or restart of unrelated engines. Offline failure retains installed
game. Subsequent direct native bundles use the same companion. Keep test helpers
and production service homes/ports separate. Rebuild the Mac ZIP and publish a
versioned release; source main reaches existing Desktop shortcuts.

## Verification

Test real HTTP auth, route isolation, malformed commands, duplicate requests,
lease replacement, and reconnection. Two independent browser contexts simulate
the laptop and 390px-wide phone, including setup, reveals, scores, strikes,
rounds, bonus hidden inputs/reveals/masking/timer, phone and board refresh,
disconnect, and the existing popup/fullscreen regressions. Exercise real App
Engine on test-only ports and judge fresh screenshots. macOS 12.6 and a physical
iPhone cannot be claimed tested without actual devices.
