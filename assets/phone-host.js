(() => {
  "use strict";
  const token = location.hash.slice(1),
    host = document.getElementById("host"),
    connection = document.getElementById("connection"),
    notice = document.getElementById("notice");
  let state = null,
    online = false,
    ended = false,
    layout = "",
    counter = 0,
    generation = 0,
    intentEpoch = 0,
    sending = false,
    reconcileFields = false,
    draftsDiscarded = false;
  let commands = [];
  const dirty = new Map(),
    saves = new Map();
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const $ = (id) => document.getElementById(id);
  const button = (text, action, args = {}, extra = "") =>
    `<button type="button" data-action="${action}" data-args="${esc(JSON.stringify(args))}" ${extra}>${esc(text)}</button>`;
  async function api(path, body) {
    const controller = new AbortController(),
      timeout = setTimeout(() => controller.abort(), 2200);
    try {
      const response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: {
          Authorization: "Bearer " + token,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) {
        const e = new Error("Request failed");
        e.status = response.status;
        throw e;
      }
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }
  function discardCommands(predicate = () => true) {
    commands = commands.filter((job) => {
      if (!predicate(job)) return true;
      job.resolve(false);
      return false;
    });
  }
  function discardDrafts() {
    if (dirty.size) draftsDiscarded = true;
    dirty.clear();
    saves.forEach(clearTimeout);
    saves.clear();
    intentEpoch++;
    // Recovery replaces even a formerly focused draft with the authoritative value.
    reconcileFields = true;
  }
  function updateGeneration(value) {
    if (Number.isSafeInteger(value) && value >= generation) generation = value;
  }
  function enabled(value) {
    online = value;
    if (!value) {
      // Connection recovery starts with fresh user intent, never an old backlog.
      discardCommands();
      discardDrafts();
    }
    host.querySelectorAll("button,input,select").forEach((el) => {
      el.disabled = !value || el.dataset.unavailable === "true";
    });
  }
  function send(action, args = {}) {
    if (!online || ended) return Promise.resolve(false);
    if (action === "bonusReset")
      discardCommands((job) => job.command.action === "bonusSet");
    if (commands.length >= 12) {
      discardDrafts();
      notice.textContent =
        "Too many pending actions. Wait for the board, then try again.";
      return Promise.resolve(false);
    }
    // Capture values now: later field edits or reset responses must not rewrite queued intent.
    const command = {
      id:
        Date.now().toString(36) +
        "_" +
        Math.random().toString(36).slice(2, 12) +
        "_" +
        ++counter,
      action,
      args: JSON.parse(JSON.stringify(args)),
    };
    if (action === "bonusSet") command.generation = generation;
    return new Promise((resolve) => {
      commands.push({ command, resolve, queuedAt: Date.now() });
      drainCommands();
    });
  }
  async function submit(command) {
    // The same ID is the acceptance ordering point, even if the first response was lost.
    for (let attempt = 0; attempt < 2; attempt++) {
      if (!online || ended) return false;
      try {
        const result = await api("command", command);
        updateGeneration(result.generation);
        notice.textContent = "";
        return true;
      } catch (e) {
        if (e.status === 403) {
          finish();
          return false;
        }
        if (e.status || attempt === 1 || !online || ended) {
          notice.textContent =
            e.status === 400 || e.status === 409
              ? "That action is out of date. Check the board and try again."
              : "Action was not confirmed. Check the board before trying again.";
          return false;
        }
      }
    }
    return false;
  }
  async function drainCommands() {
    if (sending) return;
    sending = true;
    try {
      while (commands.length && online && !ended) {
        const job = commands.shift();
        if (Date.now() - job.queuedAt > 3500) {
          job.resolve(false);
          discardCommands();
          discardDrafts();
          notice.textContent =
            "Pending actions expired. Check the board before trying again.";
          break;
        }
        const accepted = await submit(job.command);
        job.resolve(accepted);
        if (!accepted) {
          // A failed save cannot be followed by a dependent reveal, navigation, or reset.
          discardCommands();
          discardDrafts();
          break;
        }
      }
    } finally {
      sending = false;
    }
  }
  function finish() {
    ended = true;
    enabled(false);
    connection.classList.remove("live");
    connection.textContent =
      "Phone disconnected. Scan Connect phone on the laptop to pair again.";
    notice.textContent = "";
  }
  function field(id, value) {
    const el = $(id);
    if (!el) return;
    if (reconcileFields) {
      el.value = value;
      return;
    }
    if (dirty.has(id)) {
      if (String(value) === dirty.get(id)) dirty.delete(id);
      else return;
    }
    if (document.activeElement !== el) el.value = value;
  }
  function teamHTML(i) {
    return /* HTML */ `<section>
      <h3 id="name${i}"></h3>
      <div class="score" id="score${i}"></div>
      <div class="team-state" id="teamState${i}"></div>
      <div class="row">
        ${button("Control", "active", { team: i })}${button("Buzz", "buzz", { team: i })}
      </div>
      <div class="row">
        ${button("Strike", "strike", { team: i }, 'class="danger"')}${button("Undo X", "unstrike", { team: i })}
      </div>
      ${button("Award pot", "award", { team: i, round: state.main.r }, `id="award${i}" class="primary"`)}<label
        for="scoreInput${i}"
        >Set score</label
      >
      <div class="row">
        <input
          id="scoreInput${i}"
          type="number"
          min="-999999"
          max="999999"
          inputmode="numeric"
          aria-label="Team ${i + 1} score"
        /><button data-score="${i}">Save</button>
      </div>
    </section>`;
  }
  function bonusRowHTML(p, question, i) {
    const surveyAnswers = question.a
      .map(
        ([answer, points]) => /* HTML */ `
          <button data-answer="${esc(answer)}" data-points="${points}">
            ${esc(answer)} · ${points}
          </button>
        `,
      )
      .join("");
    return /* HTML */ `
      <div class="bonus-row" data-p="${p}" data-i="${i}">
        <h3>${i + 1}. ${esc(question.q)}</h3>
        <div class="entry">
          <div>
            <label for="text${p}_${i}">Private answer</label>
            <input
              id="text${p}_${i}"
              data-entry="text"
              maxlength="200"
              autocomplete="off"
            />
          </div>
          <div>
            <label for="pts${p}_${i}">Points</label>
            <input
              id="pts${p}_${i}"
              data-entry="pts"
              type="number"
              min="0"
              max="999"
              inputmode="numeric"
            />
          </div>
        </div>
        <div class="chips">${surveyAnswers}</div>
        <small id="rowStatus${p}_${i}">Hidden from audience</small>
        <div class="row">
          ${button("Reveal", "bonusReveal", { p, i }, 'class="primary"')}
          ${button("Hide", "bonusHide", { p, i })}
        </div>
      </div>
    `;
  }
  function bonusHTML(p) {
    const rows = state.questions
      .map((question, i) => bonusRowHTML(p, question, i))
      .join("");
    return /* HTML */ `
      <section>
        <h2>Player ${p + 1}</h2>
        ${button("Reveal all player " + (p + 1), "bonusRevealAll", { p })}
        ${rows}
      </section>
    `;
  }
  function render() {
    const s = state,
      m = s.main,
      b = s.bonus,
      round = s.rounds[m.r];
    const key = s.screen + ":" + m.r;
    if (layout !== key) {
      // New DOM fields always start from board data, never detached-input draft metadata.
      dirty.clear();
      reconcileFields = true;
      layout = key;
      const nav =
        s.screen === "setup"
          ? ""
          : `<nav>${button("Main game", "screen", { screen: "game" }, s.screen === "game" ? 'class="chosen"' : "")}${button("Bonus round", "screen", { screen: "bonus" }, s.screen === "bonus" ? 'class="chosen"' : "")}</nav>`;
      let content = "";
      if (s.screen === "setup")
        content = /* HTML */ `<section>
          <h2>Ready to raise the stakes?</h2>
          <p class="muted">
            Name your teams, then host the whole game here. Answers stay private
            until you reveal them.
          </p>
          <label for="teamName0">Team 1 name</label
          ><input id="teamName0" maxlength="60" value="The Ghouls" /><label
            for="teamName1"
            >Team 2 name</label
          ><input id="teamName1" maxlength="60" value="The Goblins" />
          <div class="row">
            <button id="start" class="primary">Start the game</button>
          </div>
        </section>`;
      if (s.screen === "game")
        content = /* HTML */ `<section>
            <div class="muted">
              ROUND ${m.r + 1} OF ${s.rounds.length} · PRIVATE ANSWERS
            </div>
            <h2>${esc(round.q)}</h2>
            <div class="pot" id="pot"></div>
            <div class="answers">
              ${round.a.map(([text, pts], i) => `<div class="answer"><div class="answer-copy"><strong>${i + 1}. ${esc(text)}</strong><small>${pts} survey points</small></div>${button("Reveal", "reveal", { i, round: m.r }, `id="reveal${i}" class="primary"`)}</div>`).join("")}
            </div>
            <div class="row">
              ${button("Reveal remaining", "revealRemaining", { round: m.r })}
            </div>
          </section>
          <div class="teams">${teamHTML(0)}${teamHTML(1)}</div>
          <section>
            <h3>Round controls</h3>
            <label for="roundSelect">Choose round</label
            ><select id="roundSelect">
              ${s.rounds.map((r, i) => `<option value="${i}">${i + 1}. ${esc(r.q)}</option>`).join("")}
            </select>
            <div class="row">
              ${button("Previous", "round", { i: Math.max(0, m.r - 1) }, m.r === 0 ? 'data-unavailable="true"' : "")}${button("Next round", "round", { i: Math.min(s.rounds.length - 1, m.r + 1) }, m.r === s.rounds.length - 1 ? 'data-unavailable="true"' : "")}
            </div>
            <div class="row">
              ${button("Hide question", "question", {}, 'id="question"')}${button("Points ×1", "multiplier", {}, 'id="multiplier"')}
            </div>
            <div class="row">
              ${button("Reset buzzers", "resetBuzz")}${button("Sound on", "sound", {}, 'id="sound"')}
            </div>
          </section>`;
      if (s.screen === "bonus")
        content = /* HTML */ `<section>
            <div class="muted">FAST FRIGHT · PRIVATE ANSWERS</div>
            <h2>Bonus round</h2>
            <div class="timer" id="time"></div>
            <p id="bonusTotal"></p>
            <div class="row">
              ${button("Start 20 sec", "timer", { seconds: 20 }, 'class="primary"')}${button("Start 25 sec", "timer", { seconds: 25 }, 'class="primary"')}${button("Stop", "timerStop")}
            </div>
            <div class="row">
              <button data-timer-reset="true">Reset timer to 20</button>
            </div>
            <small>The 25-second timer hides player 1 from the audience.</small>
            <div class="row">
              ${button("Hide player 1", "bonusMask", {}, 'id="mask"')}${button("Duplicate buzz", "duplicateBuzz")}
            </div>
          </section>
          ${bonusHTML(0)}${bonusHTML(1)}
          <section>
            <div class="row">
              ${button("Sound on", "sound", {}, 'id="sound"')}${button("Clear bonus board", "bonusReset", {}, 'class="danger"')}
            </div>
          </section>`;
      host.innerHTML =
        nav +
        content +
        `<div class="footer">${button("Disconnect phone", "disconnect", {}, 'class="danger"')}</div>`;
    }
    if (s.screen === "game") {
      $("pot").textContent =
        `Pot: ${m.pot} · Points ×${m.multOverride[m.r] || round.mult}${m.awarded ? " · Awarded" : ""}`;
      round.a.forEach((_, i) => {
        const el = $("reveal" + i);
        el.textContent = m.revealed.includes(i) ? "Revealed" : "Reveal";
        el.dataset.unavailable = String(m.revealed.includes(i));
      });
      m.teams.forEach((team, i) => {
        $("name" + i).textContent = team.name;
        $("score" + i).textContent = team.score;
        $("teamState" + i).textContent =
          `${team.strikes} / 3 strikes${m.active === i ? " · In control" : ""}${m.buzz === i ? " · Buzzed first" : ""}`;
        field("scoreInput" + i, team.score);
        $("award" + i).dataset.unavailable = String(m.awarded || m.pot === 0);
      });
      field("roundSelect", m.r);
      $("question").textContent = m.showQ ? "Hide question" : "Show question";
      $("multiplier").textContent =
        "Points ×" + (m.multOverride[m.r] || round.mult);
    }
    if (s.screen === "bonus") {
      $("time").textContent =
        b.left + " sec" + (b.running ? " · Running" : " · Paused");
      $("bonusTotal").textContent =
        "Revealed total: " +
        b.rows.flat().reduce((sum, r) => sum + (r.ptsShown ? r.pts : 0), 0) +
        " / 200 points";
      $("mask").textContent = b.mask ? "Show player 1" : "Hide player 1";
      b.rows.forEach((rows, p) =>
        rows.forEach((r, i) => {
          field(`text${p}_${i}`, r.text);
          field(`pts${p}_${i}`, r.pts);
          $(`rowStatus${p}_${i}`).textContent = r.shown
            ? r.ptsShown
              ? "Answer + points on screen"
              : "Answer on screen · points following"
            : "Hidden from audience";
        }),
      );
    }
    if ($("sound"))
      $("sound").textContent = s.soundOn ? "Sound on" : "Sound off";
    reconcileFields = false;
    enabled(online);
  }
  async function saveRow(row) {
    const p = +row.dataset.p,
      i = +row.dataset.i,
      text = $(`text${p}_${i}`).value,
      pts = Math.max(
        0,
        Math.min(999, Math.round(+$(`pts${p}_${i}`).value || 0)),
      );
    for (const [id, value] of [
      [`text${p}_${i}`, text],
      [`pts${p}_${i}`, pts],
    ])
      dirty.set(id, String(value));
    return await send("bonusSet", { p, i, text, pts });
  }
  function scheduleSave(row) {
    const key = row.dataset.p + "_" + row.dataset.i;
    clearTimeout(saves.get(key));
    saves.set(
      key,
      setTimeout(() => {
        saves.delete(key);
        if (row.isConnected) saveRow(row);
      }, 300),
    );
  }
  host.addEventListener("input", (e) => {
    if (e.target.tagName === "INPUT") dirty.set(e.target.id, e.target.value);
    if (!e.target.dataset.entry) return;
    const row = e.target.closest(".bonus-row");
    if (e.target.dataset.entry === "text") {
      const q = state.questions[+row.dataset.i],
        norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
      const match = q.a.find(([a]) => norm(a) === norm(e.target.value));
      const pts = $(`pts${row.dataset.p}_${row.dataset.i}`);
      pts.value = match ? match[1] : 0;
      dirty.set(pts.id, pts.value);
    }
    scheduleSave(row);
  });
  host.addEventListener("change", (e) => {
    if (e.target.id === "roundSelect") send("round", { i: +e.target.value });
  });
  host.addEventListener("click", async (e) => {
    const el = e.target.closest("button");
    if (!el || el.disabled) return;
    let epoch = intentEpoch;
    if (el.id === "start") {
      await send("start", {
        names: [$("teamName0").value.trim(), $("teamName1").value.trim()],
      });
      return;
    }
    if (el.dataset.score !== undefined) {
      const i = +el.dataset.score;
      await send("score", {
        team: i,
        score: Math.max(
          -999999,
          Math.min(999999, Math.round(+$("scoreInput" + i).value || 0)),
        ),
      });
      return;
    }
    if (el.dataset.timerReset) {
      if ((await send("timer", { seconds: 20 })) && epoch === intentEpoch)
        await send("timerStop");
      return;
    }
    const row = el.closest(".bonus-row");
    if (el.dataset.answer !== undefined) {
      $(`text${row.dataset.p}_${row.dataset.i}`).value = el.dataset.answer;
      $(`pts${row.dataset.p}_${row.dataset.i}`).value = el.dataset.points;
      await saveRow(row);
      return;
    }
    const action = el.dataset.action;
    if (!action) return;
    if (
      action === "bonusReset" &&
      !confirm("Clear every bonus-round answer and reset the timer?")
    )
      return;
    if (
      action === "disconnect" &&
      !confirm("Disconnect this phone and return controls to the laptop?")
    )
      return;
    if (action === "bonusReset") {
      epoch = ++intentEpoch;
      saves.forEach(clearTimeout);
      saves.clear();
      dirty.clear();
    }
    if (["bonusRevealAll", "screen"].includes(action)) {
      // Flush edits before revealing a whole player or removing the entry fields.
      for (const pendingRow of host.querySelectorAll(".bonus-row")) {
        const key = pendingRow.dataset.p + "_" + pendingRow.dataset.i;
        if (!saves.has(key)) continue;
        clearTimeout(saves.get(key));
        saves.delete(key);
        if (!(await saveRow(pendingRow)) || epoch !== intentEpoch) return;
      }
    }
    if (row && ["bonusReveal", "bonusHide"].includes(action)) {
      const key = row.dataset.p + "_" + row.dataset.i;
      clearTimeout(saves.get(key));
      saves.delete(key);
      if (!(await saveRow(row)) || epoch !== intentEpoch) return;
    }
    if (
      (await send(action, JSON.parse(el.dataset.args || "{}"))) &&
      action === "disconnect"
    )
      finish();
  });
  async function poll() {
    if (ended) return;
    try {
      if (!token) throw { status: 403 };
      const result = await api("state");
      if (ended) return; // A poll already in flight must not undo explicit disconnect.
      updateGeneration(result.generation);
      state = result.state;
      online = Boolean(result.board_connected && state);
      connection.textContent = online
        ? "Connected · Laptop is the contestant board"
        : "Laptop board disconnected. Reopen the game to reconnect.";
      connection.classList.toggle("live", online);
      if (state) render();
      else enabled(false);
      if (online && draftsDiscarded) {
        notice.textContent =
          "Unsent edits were discarded; answers now match the laptop.";
        draftsDiscarded = false;
      }
    } catch (e) {
      if (e.status === 403) {
        finish();
        return;
      }
      enabled(false);
      connection.classList.remove("live");
      connection.textContent =
        "Connection lost. Keep both devices on the same Wi-Fi. Reconnecting…";
    }
    setTimeout(poll, 400);
  }
  poll();
})();
