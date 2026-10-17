/* Local authoritative board adapter. Phone actions are a fixed, bounded interface. */
(() => {
  "use strict";
  const token = new URLSearchParams(location.hash.slice(1)).get("ff_board");
  let lease = null,
    stopped = false,
    paired = false,
    disconnecting = false,
    ack = [],
    info = null,
    pairingWindow = null,
    pairingBlocked = false;
  const seen = new Set();
  const button = document.createElement("button");
  button.id = "phoneConnect";
  button.className = "btn";
  button.textContent = "Connect phone";
  document.querySelector("nav").appendChild(button);
  const status = document.createElement("div");
  status.id = "phoneStatus";
  status.setAttribute("role", "status");
  document.querySelector("header").after(status);
  const style = document.createElement("style");
  style.textContent = /* CSS */ `#phoneStatus{text-align:center;color:var(--candle);padding:.25rem;font-size:.9rem}#phoneStatus:empty{display:none}.phone-audience nav button:not(#fsBtn):not(#phoneConnect),.phone-audience #setup,.phone-audience .controls,.phone-audience .keys,.phone-audience .teamctrl,.phone-audience .hint{display:none!important}.phone-audience .team,.phone-audience .tile,.phone-audience .fmrow,.phone-audience .xslot{pointer-events:none}.phone-audience .xslot{cursor:default}`;
  document.head.appendChild(style);
  const pairingURL = new URL("assets/phone-pair.html", location.href).href;
  function openPairingWindow() {
    try {
      if (pairingWindow && !pairingWindow.closed &&
          (pairingWindow.document.URL === "about:blank" ||
           pairingWindow.location.href === pairingURL)) {
        pairingWindow.focus();
        return pairingWindow;
      }
    } catch (e) {
      // A window navigated elsewhere belongs to the user; open a fresh one.
    }
    const popup = window.open(pairingURL, "", "popup=yes,width=520,height=760,resizable=yes,scrollbars=yes");
    if (!popup) return null;
    pairingWindow = popup;
    return popup;
  }
  function closePairingWindow() {
    try {
      if (pairingWindow && !pairingWindow.closed &&
          (pairingWindow.document.URL === "about:blank" ||
           pairingWindow.location.href === pairingURL)) pairingWindow.close();
    } catch (e) {}
    pairingWindow = null;
  }
  window.addEventListener("pagehide", closePairingWindow);
  window.addEventListener("message", (event) => {
    if (event.origin === location.origin && event.source === pairingWindow &&
        event.data && event.data.type === "ff-pair-ready")
      renderPairingWindow(pairingWindow);
  });
  function audience(value) {
    paired = value;
    document.body.classList.toggle("phone-audience", value);
  }
  const pairingKey = "ff_phone_paired_" + token;
  const rememberPairing = (value) => {
    try {
      if (value) sessionStorage.setItem(pairingKey, "1");
      else sessionStorage.removeItem(pairingKey);
    } catch (e) {}
  };
  const wasPaired = () => {
    try {
      return sessionStorage.getItem(pairingKey) === "1";
    } catch (e) {
      return false;
    }
  };
  // Capture before the original local game shortcuts and click handlers.
  document.addEventListener(
    "keydown",
    (e) => {
      if (paired || stopped) {
        e.stopImmediatePropagation();
      }
    },
    true,
  );
  document.addEventListener(
    "click",
    (e) => {
      if (
        (paired || stopped) &&
        !e.target.closest("#phoneConnect,#fsBtn,#splash")
      ) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true,
  );
  async function api(path, body) {
    const controller = new AbortController(),
      timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const response = await fetch("/phone/" + path, {
        method: body ? "POST" : "GET",
        headers: {
          Authorization: "Bearer " + token,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) {
        const error = new Error("Phone service " + response.status);
        error.status = response.status;
        throw error;
      }
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }
  function snapshot() {
    return {
      version: 2,
      series: { game: S.g, started: S.started, results: RESULTS.map(r => ({...r})) },
      screen:
        ["setup", "game", "bonus"].find(
          (id) => !$(id).classList.contains("hidden"),
        ) || "setup",
      main: {
        ...Object.fromEntries(Object.entries(S).filter(([key]) => !["g", "started"].includes(key))),
        teams: S.teams.map((t) => ({ ...t })),
        revealed: [...S.revealed],
        multOverride: { ...S.multOverride },
      },
      bonus: {
        rows: FM.rows.map((rows) => rows.map((r) => ({ ...r }))),
        mask: FM.mask,
        left: FM.left,
        running: FM.timer !== null,
      },
      rounds: ROUNDS,
      questions: BONUS,
      soundOn,
    };
  }
  function restore(state) {
    if (!state || ![1,2].includes(state.version)) return;
    // Old eight-round snapshots cannot map safely onto the new three-round games.
    if (state.version === 1) return;
    S.g = state.series.game;
    S.started = state.series.started;
    ROUNDS = GAMES[S.g].rounds;
    BONUS = GAMES[S.g].bonus;
    if (validResults(state.series.results)) RESULTS = state.series.results;
    stopTimer();
    cancelBonusReveals();
    Object.assign(S, state.main);
    S.revealed = new Set(state.main.revealed);
    FM.rows = state.bonus.rows;
    FM.mask = state.bonus.mask;
    FM.left = state.bonus.left;
    soundOn = state.soundOn;
    $("soundBtn").textContent = soundOn ? "Sound on" : "Sound off";
    $("soundBtn").classList.toggle("on", soundOn);
    buildBoard();
    S.revealed.forEach((i) => $("board").children[i].classList.add("flipped"));
    render();
    fmRender();
    drawTimer();
    renderSetup();
    if (state.screen === "bonus") goBonus(); else show(state.screen);
    sendState(true);
  }
  const integer = (v, low, high) =>
    Number.isInteger(v) && v >= low && v <= high;
  function execute(command) {
    const a = command.args,
      action = command.action;
    if (!a || typeof a !== "object" || command.game !== S.g) return;
    const team = integer(a.team, 0, 1),
      row =
        integer(a.p, 0, 1) && integer(a.i, 0, BONUS.length - 1)
          ? FM.rows[a.p][a.i]
          : null;
    if (
      ["reveal", "revealRemaining", "award"].includes(action) &&
      a.round !== S.r
    )
      return;
    switch (action) {
      case "selectGame":
        if (!$("setup").classList.contains("hidden") && integer(a.game, 0, GAMES.length-1)) selectGame(a.game);
        break;
      case "finishGame":
        finishGame();
        break;
      case "clearResults":
        if (!$("setup").classList.contains("hidden")) clearResults();
        break;
      case "start":
        if (
          !Array.isArray(a.names) ||
          a.names.length !== 2 ||
          !a.names.every((n) => typeof n === "string" && n.length <= 60)
        )
          return;
        a.names.forEach((n, i) => {
          $("t" + (i + 1)).value = n;
        });
        $("startBtn").onclick();
        break;
      case "screen":
        if (a.screen === "setup") goSetup();
        else if (S.started && a.screen === "bonus") goBonus();
        else if (S.started && a.screen === "game") show("game");
        break;
      case "round":
        if (integer(a.i, 0, ROUNDS.length - 1)) loadRound(a.i);
        break;
      case "reveal":
        if (integer(a.i, 0, ROUNDS[S.r].a.length - 1)) reveal(a.i);
        break;
      case "revealRemaining":
        $("revealAll").onclick();
        break;
      case "strike":
        if (team) strike(a.team);
        break;
      case "unstrike":
        if (team) {
          S.teams[a.team].strikes = Math.max(0, S.teams[a.team].strikes - 1);
          render();
        }
        break;
      case "active":
        if (team) {
          S.active = a.team;
          render();
        }
        break;
      case "award":
        if (team) award(a.team);
        break;
      case "score":
        if (team && integer(a.score, -999999, 999999)) {
          S.teams[a.team].score = a.score;
          render();
        }
        break;
      case "buzz":
        if (team) buzzIn(a.team);
        break;
      case "resetBuzz":
        $("resetBuzz").onclick();
        break;
      case "question":
        $("toggleQ").onclick();
        break;
      case "multiplier":
        $("multBtn").onclick();
        break;
      case "sound":
        $("soundBtn").onclick();
        break;
      case "bonusSet":
        if (
          row &&
          typeof a.text === "string" &&
          a.text.length <= 200 &&
          integer(a.pts, 0, 999)
        ) {
          row.text = a.text;
          row.pts = a.pts;
          if (!row.text) {
            row.shown = false;
            row.ptsShown = false;
          }
          fmRender();
        }
        break;
      case "bonusReveal":
        if (row) revealRow(a.p, a.i);
        break;
      case "bonusHide":
        if (row) {
          row.shown = false;
          row.ptsShown = false;
          fmRender();
        }
        break;
      case "bonusRevealAll":
        if (integer(a.p, 0, 1)) revealBonusPlayer(a.p);
        break;
      case "timer":
        if (a.seconds === 20 || a.seconds === 25) {
          if (a.seconds === 25) FM.mask = true;
          fmRender();
          startTimer(a.seconds);
        }
        break;
      case "timerStop":
        stopTimer();
        break;
      case "bonusMask":
        FM.mask = !FM.mask;
        fmRender();
        break;
      case "bonusReset":
        stopTimer();
        FM.left = 20;
        drawTimer();
        fmInit();
        break;
      case "duplicateBuzz":
        SFX.buzz();
        break;
      case "disconnect":
        disconnecting = true;
        break;
    }
    sendState();
  }
  async function pairingInfo() {
    info = await api("info");
    return info;
  }
  button.onclick = () => {
    // Open during the click gesture, before awaiting the companion response.
    const popup = openPairingWindow();
    if (!popup) {
      pairingBlocked = true;
      status.textContent = "Allow pop-ups for this game, then click Connect phone again.";
      return;
    }
    if (pairingBlocked) status.textContent = "";
    pairingBlocked = false;
    // A laptop gesture unlocks audio for subsequent remote phone commands.
    const audio = ac();
    if (audio && audio.state === "suspended") audio.resume().catch(() => {});
    renderPairingWindow(popup);
  };
  async function renderPairingWindow(popup) {
    if (!popup || popup.closed || popup.location.href !== pairingURL ||
        !popup.document.getElementById("phoneInstructions")) return;
    const doc = popup.document,
      instructions = doc.getElementById("phoneInstructions"),
      qrBox = doc.getElementById("phoneQR"),
      link = doc.getElementById("phoneURL");
    const theme = getComputedStyle(document.documentElement);
    for (const name of ["--ui", "--night", "--plum", "--bone", "--candle"])
      doc.documentElement.style.setProperty(name, theme.getPropertyValue(name));
    qrBox.textContent = "";
    link.textContent = "";
    link.removeAttribute("href");
    if (!token) {
      instructions.textContent =
        "Launch Fright Feud using the Desktop shortcut to enable phone hosting. You can keep playing here with the local controls.";
      return;
    }
    try {
      const details = await pairingInfo();
      if (popup.closed) return;
      const url = details.host_urls[0];
      instructions.textContent = url
        ? "On the same Wi-Fi, scan this code with your iPhone camera and open it in Safari. No app needed."
        : "Connect the Mac and phone to the same Wi-Fi, then try Connect phone again. No usable Wi-Fi address was found.";
      if (url) {
        const qr = qrcode(0, "M");
        qr.addData(url);
        qr.make();
        qrBox.innerHTML = qr.createSvgTag(5, 16);
        link.textContent = url;
        link.href = url;
      }
    } catch (e) {
      instructions.textContent =
        "Phone companion unavailable. Relaunch using the Desktop shortcut, then try again.";
    }
  }
  if (!token) return;
  // Avoid flashing private laptop controls during refresh recovery.
  audience(true);
  status.textContent = "Connecting phone companion…";
  async function sync() {
    if (stopped) return;
    try {
      const sentAck = ack.slice(),
        result = await api("sync", { lease, state: snapshot(), ack: sentAck });
      ack = ack.filter((id) => !sentAck.includes(id));
      if (disconnecting && sentAck.length) {
        closePairingWindow();
        disconnecting = false;
        rememberPairing(false);
        audience(false);
        await pairingInfo();
      }
      if (result.host_connected) {
        if (!paired) closePairingWindow();
        rememberPairing(true);
        audience(true);
        status.textContent = pairingBlocked
          ? "Allow pop-ups for this game, then click Connect phone again."
          : "Phone host connected · Contestant board";
      } else
        status.textContent = pairingBlocked
          ? "Allow pop-ups for this game, then click Connect phone again."
          : paired
          ? "Phone disconnected · Reconnect on your phone or use Connect phone"
          : "Phone hosting ready · Connect phone to begin";
      if (result.storage_warning) status.textContent += " · " + result.storage_warning;
      for (const command of result.commands) {
        if (!seen.has(command.id)) {
          seen.add(command.id);
          if (seen.size > 2048) seen.delete(seen.values().next().value);
          execute(command);
        }
        if (!ack.includes(command.id)) ack.push(command.id);
      }
    } catch (e) {
      if (e.status === 409) {
        closePairingWindow();
        stopped = true;
        stopTimer();
        cancelBonusReveals();
        audience(true);
        status.textContent =
          "This board was replaced by another window. Use the newest game window.";
        return;
      }
      status.textContent = "Phone companion disconnected · Reconnecting…";
    }
    setTimeout(sync, 400);
  }
  (async () => {
    try {
      const claimed = await api("claim", {});
      lease = claimed.lease;
      restore(claimed.state);
      if (validResults(claimed.results)) {
        RESULTS = claimed.results;
        saveResults();
        renderSetup();
      }
      await pairingInfo();
      audience(info.host_connected || wasPaired());
      sync();
    } catch (e) {
      audience(wasPaired());
      status.textContent =
        "Phone companion unavailable · Relaunch with the Desktop shortcut";
    }
  })();
})();
