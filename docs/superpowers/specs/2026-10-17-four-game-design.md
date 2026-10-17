# Four-game format and saved results

Approved by the user: merge the downloaded game's four selectable games, each with three rounds (single/double/triple) and five bonus questions, into the repository. Preserve its splash, local fonts, layout, popup checks, reveal cancellation, Safari fullscreen fallback, and paired phone host. Never modify the downloaded HTML.

The board remains authoritative. `GAMES` contains the exact supplied question sets; `selectGame(index)`, `goSetup()`, `finishGame()` and `clearResults()` manage the series. Results contain game (1–4), team names, final team scores, and revealed bonus total; one record per game, replacing that game's previous result. Persist in localStorage and, for the companion, a private atomic results file so relaunching on a different port retains results. Storage failure must leave the current game usable and report failure.

Use phone snapshot v2 with a bounded `series: {game, started, results}` alongside the unchanged main/bonus fields. Retain v1 validation for older clients. Add bounded game selection/finish/clear commands; fence commands with the selected game and bonus generation. Restore the matching question set before rebuilding views. Game changes reset scores, strikes, multiplier overrides, bonus answers, pending reveals and timer. Host popup receives updated bonus questions for every game. Phone offers selector, results, new-game navigation and finish; no private answers on the contestant board.

Verify desktop four-game flow, persistence, escaped names, popup synchronization, phone flow, stale edits and reconnect/reload. Judge screenshots of setup/results and 390px phone. Run existing integration and transport regressions, validate manifest, package, independent review, and push main without a PR.
