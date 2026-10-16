/* Local authoritative board adapter. Phone actions are a fixed, bounded interface. */
(() => {
  "use strict";
  const token = new URLSearchParams(location.hash.slice(1)).get("ff_board");
  let lease = null,
    stopped = false,
    paired = false,
    disconnecting = false,
    ack = [],
    info = null;
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
  style.textContent = /* CSS */ `#phoneStatus{text-align:center;color:var(--candle);padding:.25rem;font-size:.9rem}#phoneStatus:empty{display:none}.phone-audience nav button:not(#fsBtn):not(#phoneConnect),.phone-audience #setup,.phone-audience .controls,.phone-audience .keys,.phone-audience .teamctrl,.phone-audience .hint{display:none!important}.phone-audience .team,.phone-audience .tile,.phone-audience .fmrow,.phone-audience .xslot{pointer-events:none}.phone-audience .xslot{cursor:default}#phonePair{position:fixed;z-index:1100;inset:0;background:#110b20eb;display:flex;align-items:center;justify-content:center;padding:20px}#phonePair[hidden]{display:none}#phonePair .pair-card{background:#291637;color:#fff;border:2px solid #ff922b;border-radius:20px;padding:24px;max-width:440px;text-align:center;max-height:95vh;overflow:auto}#phonePair svg{display:block;background:white;margin:16px auto;max-width:100%;height:auto}#phonePair a{color:#ffc779;overflow-wrap:anywhere}#phonePair button{min-height:44px;margin:12px 0}`;
  document.head.appendChild(style);
  const panel = document.createElement("div");
  panel.id = "phonePair";
  panel.hidden = true;
  panel.innerHTML = /* HTML */ `
    <div
      class="pair-card"
      role="dialog"
      aria-modal="true"
      aria-label="Connect phone"
    >
      <h2>Host from your phone</h2>
      <p id="phoneInstructions"></p>
      <div id="phoneQR"></div>
      <a id="phoneURL"></a>
      <p>Keep the phone private. The laptop becomes the contestant board.</p>
      <button class="btn" id="phonePairClose">Close</button>
    </div>
  `;
  document.body.appendChild(panel);
  $("phonePairClose").onclick = () => {
    panel.hidden = true;
  };
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
        !e.target.closest("#phoneConnect,#fsBtn,#phonePair,#splash")
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
      version: 1,
      screen:
        ["setup", "game", "bonus"].find(
          (id) => !$(id).classList.contains("hidden"),
        ) || "setup",
      main: {
        ...S,
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
    if (!state || state.version !== 1) return;
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
    show(state.screen);
    sendState(true);
  }
  const integer = (v, low, high) =>
    Number.isInteger(v) && v >= low && v <= high;
  function execute(command) {
    const a = command.args,
      action = command.action;
    if (!a || typeof a !== "object") return;
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
        if (["setup", "game", "bonus"].includes(a.screen)) show(a.screen);
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
  button.onclick = async () => {
    // A laptop gesture unlocks audio for subsequent remote phone commands.
    const audio = ac();
    if (audio && audio.state === "suspended") audio.resume().catch(() => {});
    panel.hidden = false;
    $("phoneQR").textContent = "";
    $("phoneURL").textContent = "";
    $("phoneURL").removeAttribute("href");
    if (!token) {
      $("phoneInstructions").textContent =
        "Launch Fright Feud using the Desktop shortcut to enable phone hosting. You can keep playing here with the local controls.";
      return;
    }
    try {
      await pairingInfo();
      const url = info.host_urls[0];
      $("phoneInstructions").textContent = url
        ? "On the same Wi-Fi, scan this code with your iPhone camera and open it in Safari. No app needed."
        : "Connect the Mac and phone to the same Wi-Fi, then try Connect phone again. No usable Wi-Fi address was found.";
      if (url) {
        const qr = qrcode(0, "M");
        qr.addData(url);
        qr.make();
        $("phoneQR").innerHTML = qr.createSvgTag(5, 16);
        $("phoneURL").textContent = url;
        $("phoneURL").href = url;
      }
    } catch (e) {
      $("phoneInstructions").textContent =
        "Phone companion unavailable. Relaunch using the Desktop shortcut, then try again.";
    }
  };
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
        disconnecting = false;
        rememberPairing(false);
        audience(false);
        await pairingInfo();
      }
      if (result.host_connected) {
        rememberPairing(true);
        audience(true);
        panel.hidden = true;
        status.textContent = "Phone host connected · Contestant board";
      } else
        status.textContent = paired
          ? "Phone disconnected · Reconnect on your phone or use Connect phone"
          : "Phone hosting ready · Connect phone to begin";
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
