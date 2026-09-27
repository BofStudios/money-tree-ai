/* Money: whose money is on screen, how to add or withdraw it, and the keys
 * and switch that decide which account the bot trades.
 *
 * Three rules from the phone app hold here too:
 *   - the balance always says whether it is real, practice or simulated;
 *   - this app never shows bank details or moves money — it opens Alpaca;
 *   - switching to real money is typed, not clicked, and still leaves the
 *     bot disarmed until the owner arms it.
 */

import { t, getLanguage } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("token");
  try { return fromUrl || localStorage.getItem("mt_token") || ""; } catch { return fromUrl || ""; }
})();
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch(q(path), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

const locale = () => (getLanguage() === "tr" ? "tr-TR" : "en-US");
const usd = (n) => (n === null || n === undefined || Number.isNaN(Number(n)))
  ? "—"
  : "$" + Number(n).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signedUsd = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + usd(Math.abs(n));

let money = null;       // last /api/money
let keys = null;        // last /api/keys
let withdrawFirst = false;

/* ------------------------------------------------------------ data */

let moneyAt = 0;
async function loadMoney(force = false) {
  if (!force && Date.now() - moneyAt < 10000) return;
  moneyAt = Date.now();
  try {
    money = await api("GET", "/api/money");
    renderCard();
    renderView();
  } catch { /* the rest of Home still works */ }
}

async function loadKeys() {
  try {
    keys = await api("GET", "/api/keys");
    renderSettings();
  } catch { /* settings shows what it can */ }
}

/* ------------------------------------------------------- home card */

function tagFor(broker, armed) {
  if (broker === "alpaca_live") return { cls: "real", text: `${t("mc.real")} · ${t(armed ? "mc.armed" : "mc.notArmed")}` };
  if (broker === "alpaca_paper") return { cls: "paper", text: t("mc.paper") };
  if (broker === "signal") return { cls: "paper", text: t("mc.signal") };
  return { cls: "paper", text: t("mc.sim") };
}

function renderCard() {
  const s = window.mtState;
  const card = $("moneyCard");
  if (!card || !s) return;
  const broker = s.broker || "simulation";
  const armed = s.risk && s.risk.armed;
  const tag = tagFor(broker, armed);
  const account = s.account;

  card.dataset.money = tag.cls;
  $("mcTag").className = `mc-tag ${tag.cls}`;
  $("mcTag").innerHTML = `<i></i>${esc(tag.text)}`;

  const empty = broker === "alpaca_live" && account && account.equity < 1;
  $("mcEmpty").hidden = !empty;
  $("heroEquity").hidden = empty;

  let sub = "";
  if (broker === "alpaca_live" || broker === "alpaca_paper") {
    sub = account ? t("mc.cash", { cash: usd(account.cash), bp: usd(account.buying_power) }) : "";
    if (broker === "alpaca_paper") sub = t("mc.paperBody", { equity: usd(s.equity) });
  } else if (broker === "signal") {
    sub = t("mc.signalBody");
  } else {
    sub = t("mc.simBody", { equity: usd(s.equity) });
  }
  $("mcSub").textContent = sub;

  const made = money && money.made;
  const result = $("mcResult");
  if (made && (made.trades || made.unrealised)) {
    result.hidden = false;
    result.dataset.tone = made.total > 0 ? "up" : made.total < 0 ? "down" : "flat";
    result.textContent = t(made.total < 0 ? "mc.lost" : "mc.made", { amount: signedUsd(made.total) });
  } else {
    result.hidden = false;
    result.dataset.tone = "flat";
    result.textContent = t("mc.noTrades");
  }

  const real = broker === "alpaca_live";
  $("mcActions").innerHTML = real
    ? `<button class="primary" data-money="add">${esc(t("mc.add"))}</button>
       <button class="ghost" data-money="out">${esc(t("mc.withdraw"))}</button>`
    : `<button class="ghost" data-money="add">${esc(t("mc.add"))}</button>
       <button class="link-accent" data-goto-settings>${esc(t("mc.goReal"))}</button>`;
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-back-home]")) { window.showView?.("home"); return; }
  const opener = e.target.closest("[data-money]");
  if (opener) {
    withdrawFirst = opener.dataset.money === "out";
    window.showView?.("money");
    return;
  }
  if (e.target.closest("[data-goto-settings]")) {
    window.showView?.("settings");
    setTimeout(() => $("sMoneyBlock")?.scrollIntoView({ block: "start" }), 60);
  }
});

/* ------------------------------------------------------ money view */

function step(n, text) {
  return `<li><b>${n}</b><span>${esc(text)}</span></li>`;
}

function renderView() {
  const host = $("moneyView");
  if (!host || !money) return;
  const real = money.real;
  const account = money.account;

  const summary = real
    ? `<section class="mv-card glow">
         <span class="mv-label">${esc(t("mc.inAlpaca"))}</span>
         <div class="mv-figure">${esc(account ? usd(account.equity) : "—")}</div>
         ${account ? `<div class="kv"><span>${esc(t("mv.cashLabel"))}</span><b>${esc(usd(account.cash))}</b></div>
         <div class="kv"><span>${esc(t("mv.buying"))}</span><b>${esc(usd(account.buying_power))}</b></div>` : ""}
         ${money.error ? `<p class="note warn">${esc(t("mc.unreachable", { error: money.error }))}</p>` : ""}
       </section>`
    : `<section class="mv-card soft">
         <b>${esc(t("mv.practiceTitle"))}</b>
         <p>${esc(t("mv.practiceBody"))}</p>
       </section>`;

  const made = money.made || {};
  const result = `
    <section class="mv-card">
      <span class="mv-label">${esc(t("mv.result"))}</span>
      <div class="mv-figure ${made.total > 0 ? "up" : made.total < 0 ? "down" : ""}">${esc(signedUsd(made.total || 0))}</div>
      <div class="kv"><span>${esc(t("mv.realised"))}</span><b>${esc(signedUsd(made.realised || 0))}</b></div>
      <div class="kv"><span>${esc(t("mv.unrealised"))}</span><b>${esc(signedUsd(made.unrealised || 0))}</b></div>
    </section>`;

  const unmanaged = (money.unmanaged || []).length ? `
    <section class="mv-card">
      <span class="mv-label">${esc(t("mv.notMine"))}</span>
      <p class="note faint">${esc(t("mv.notMineBody"))}</p>
      ${money.unmanaged.map((h) => `<div class="kv"><span>${esc(h.symbol)} · ${esc(h.qty)}</span><b>${esc(signedUsd(h.unrealized_pl))}</b></div>`).join("")}
    </section>` : "";

  const openAlpaca = `<a class="primary wide" href="${esc(money.alpaca_url)}" target="_blank" rel="noopener">${esc(t("mc.openAlpaca"))}</a>`;
  const deposit = `
    <h3 class="mv-section">${esc(t("mv.addTitle"))}</h3>
    <section class="mv-card"><ol class="mv-steps">
      ${step(1, t("mv.add1"))}${step(2, t("mv.add2"))}${step(3, t("mv.add3"))}${step(4, t("mv.add4"))}
    </ol>${openAlpaca}</section>`;
  const smallCash = real && account && account.cash >= 0 && account.cash <= 50
    ? `<p class="mv-callout">${esc(t("mv.smallCash", { cash: usd(account.cash) }))}</p>` : "";
  const withdraw = `
    <h3 class="mv-section">${esc(t("mv.outTitle"))}</h3>
    <section class="mv-card"><ol class="mv-steps">
      ${step(1, t("mv.out1"))}${step(2, t("mv.out2"))}${step(3, t("mv.out3"))}
    </ol>${smallCash}${openAlpaca}</section>`;

  host.innerHTML = `
    ${summary}
    ${result}
    ${unmanaged}
    ${withdrawFirst ? withdraw + deposit : deposit + withdraw}
    <section class="mv-card warn-card">
      <b>${esc(t("mv.neverTitle"))}</b>
      <p>${esc(t("mv.neverBody"))}</p>
    </section>
    <p class="note faint">${esc(t("mv.source"))}</p>
    <a class="link-accent" href="https://alpaca.markets/learn/fund-live-trading-account" target="_blank" rel="noopener">${esc(t("mv.guide"))}</a>`;
}

/* -------------------------------------------------------- settings */

function keyState(view) {
  if (!view || !view.set) return t("sm.keyNone");
  if (view.problem) return t("sm.keyRefused", { why: view.problem });
  return t(view.source === "env" ? "sm.keyEnv" : "sm.keySet", { tail: view.tail || "····" });
}

function keyForm(account) {
  const view = keys && keys[`alpaca_${account}`];
  const title = t(account === "live" ? "sm.liveKeys" : "sm.paperKeys");
  // A pair Alpaca refused is as good as none: ask for new ones straight away.
  const usable = Boolean(view && view.set && !view.problem);
  return `
    <div class="key-row" data-account="${account}">
      <div class="key-head">
        <b>${esc(title)}</b>
        <span class="key-state ${usable ? "on" : view && view.problem ? "bad" : ""}">${esc(keyState(view))}</span>
      </div>
      <form class="key-form" data-key-form="${account}" ${usable ? "hidden" : ""}>
        <input name="key" autocomplete="off" spellcheck="false" placeholder="${esc(t("sm.keyId"))}">
        <input name="secret" type="password" autocomplete="off" spellcheck="false" placeholder="${esc(t("sm.secret"))}">
        <button type="submit" class="primary sm">${esc(t("sm.check"))}</button>
      </form>
      <div class="key-actions" ${usable ? "" : "hidden"}>
        <button class="ghost sm" data-key-replace="${account}">${esc(t("sm.replace"))}</button>
        ${view && view.source === "app" ? `<button class="ghost sm danger-text" data-key-remove="${account}">${esc(t("sm.remove"))}</button>` : ""}
      </div>
      <p class="note key-note" data-key-note="${account}"></p>
    </div>`;
}

function renderSettings() {
  const host = $("sMoney");
  const s = window.mtState;
  if (!host || !s) return;
  const mode = s.mode;
  const inUse = (keys && keys.in_use) || s.broker;

  host.innerHTML = `
    <div class="field-block">
      <label>${esc(t("sm.mode"))}</label>
      <div class="seg-row" id="modeRow">
        ${["paper", "live", "signal"].map((m) => `
          <button class="seg ${mode === m ? "active" : ""} ${m === "live" ? "seg-real" : ""}" data-set-mode="${m}">
            ${esc(t({ paper: "sm.modePaper", live: "sm.modeLive", signal: "sm.modeSignal" }[m]))}
          </button>`).join("")}
      </div>
      <p class="note faint">${esc(t(`sm.modeHint.${mode}`))}</p>
      <p class="note">${esc(t("sm.inUse", { what: t(`sm.use.${inUse}`) }))}</p>
    </div>
    ${keys && keys.restart_needed ? `
      <div class="restart-banner">
        <span>${esc(t("sm.restartNeeded"))}</span>
        <button class="primary sm" data-restart>${esc(t("sm.restart"))}</button>
      </div>` : ""}
    ${keyForm("paper")}
    ${keyForm("live")}
    <p class="note faint">${esc(t("sm.where"))}</p>
    <p class="note faint">${esc(t("sm.encrypted"))}</p>`;
}

document.addEventListener("submit", async (e) => {
  const form = e.target.closest("[data-key-form]");
  if (!form) return;
  e.preventDefault();
  const account = form.dataset.keyForm;
  const note = document.querySelector(`[data-key-note="${account}"]`);
  const button = form.querySelector("button");
  button.disabled = true;
  note.className = "note key-note";
  note.textContent = t("sm.checking");
  try {
    const result = await api("POST", "/api/keys/alpaca", {
      account, key: form.key.value, secret: form.secret.value,
    });
    form.reset();
    await loadKeys();
    const fresh = document.querySelector(`[data-key-note="${account}"]`);
    if (fresh) {
      fresh.className = "note key-note good";
      fresh.textContent = t("sm.saved", { status: result.account.status, equity: usd(result.account.equity) });
    }
  } catch (err) {
    note.className = "note key-note bad";
    note.textContent = err.message;
    button.disabled = false;
  }
});

document.addEventListener("click", async (e) => {
  const replace = e.target.closest("[data-key-replace]");
  if (replace) {
    const row = replace.closest(".key-row");
    row.querySelector(".key-form").hidden = false;
    row.querySelector(".key-actions").hidden = true;
    row.querySelector("input[name=key]").focus();
    return;
  }
  const remove = e.target.closest("[data-key-remove]");
  if (remove) {
    remove.disabled = true;
    try { await api("DELETE", `/api/keys/alpaca/${remove.dataset.keyRemove}`); } catch (err) {
      window.showAlert?.({ tone: "bad", title: err.message });
    }
    loadKeys();
    return;
  }
  if (e.target.closest("[data-restart]")) {
    try { await api("POST", "/api/restart"); waitForRestart(); } catch (err) {
      window.showAlert?.({ tone: "bad", title: err.message });
    }
    return;
  }
  const modeButton = e.target.closest("[data-set-mode]");
  if (modeButton) {
    const mode = modeButton.dataset.setMode;
    const s = window.mtState || {};
    if (mode === s.mode) return;
    if (mode === "live") { confirmReal(); return; }
    try { await api("POST", "/api/mode", { mode }); waitForRestart(); } catch (err) {
      window.showAlert?.({ tone: "bad", title: err.message });
    }
  }
});

/* Real money is typed, not clicked. */
function confirmReal() {
  if (!(keys && keys.alpaca_live && keys.alpaca_live.set)) {
    window.showAlert?.({ tone: "bad", title: t("sm.needLive") });
    return;
  }
  const word = t("sm.confirmWord");
  const box = $("confirmReal");
  box.hidden = false;
  box.innerHTML = `
    <div class="confirm-card">
      <h2>${esc(t("sm.confirmTitle"))}</h2>
      <p>${esc(t("sm.confirmBody", { word }))}</p>
      <input id="confirmWord" autocomplete="off" spellcheck="false" placeholder="${esc(word)}">
      <div class="onboard-actions">
        <button class="primary danger" id="confirmGo" disabled>${esc(t("sm.confirmGo"))}</button>
        <button class="ghost" id="confirmCancel">${esc(t("sm.cancel"))}</button>
      </div>
      <p class="note bad" id="confirmError"></p>
    </div>`;
  const input = $("confirmWord");
  input.focus();
  input.addEventListener("input", () => {
    $("confirmGo").disabled = input.value.trim().toLocaleUpperCase(locale()) !== word.toLocaleUpperCase(locale());
  });
  $("confirmCancel").onclick = () => { box.hidden = true; };
  $("confirmGo").onclick = async () => {
    $("confirmGo").disabled = true;
    try {
      await api("POST", "/api/mode", { mode: "live", confirm: true });
      box.hidden = true;
      waitForRestart();
    } catch (err) {
      $("confirmError").textContent = err.message;
    }
  };
}

/* The server goes away and comes back; the page follows it. In the desktop
   window the whole app restarts, so this mostly matters on a phone. */
function waitForRestart() {
  const overlay = $("restartOverlay");
  overlay.hidden = false;
  $("restartText").textContent = t("sm.restarting");
  let wentDown = false;
  const started = Date.now();
  const timer = setInterval(async () => {
    try {
      const res = await fetch(q("/api/status"), { cache: "no-store" });
      if (res.ok && (wentDown || Date.now() - started > 8000)) {
        clearInterval(timer);
        location.reload();
      }
    } catch {
      wentDown = true;
      $("restartText").textContent = t("sm.back");
    }
  }, 1000);
}

/* ---------------------------------------------------------- wiring */

window.addEventListener("mt:status", () => {
  renderCard();
  if (!keys) loadKeys(); else renderSettings();
  loadMoney();
});

window.addEventListener("mt:ws", (e) => {
  const type = e.detail.type;
  if (type === "trade_closed" || type === "trade_opened") loadMoney(true);
});

window.addEventListener("mt:view", (e) => {
  if (e.detail === "money") loadMoney(true);
  if (e.detail === "settings") loadKeys();
});

window.addEventListener("mt:lang", () => {
  renderCard();
  renderView();
  renderSettings();
});

loadMoney(true);
loadKeys();
