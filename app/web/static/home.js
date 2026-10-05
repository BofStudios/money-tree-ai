/* The phone-first home: what the bot is doing, what it wants, what it made.
 *
 * chart.js owns the socket and the status polling. This module only listens
 * (mt:status, mt:line, mt:ws) and draws, so there is still exactly one source
 * of truth for the bot's state. It is a module so it can use the translations.
 *
 * It also runs the first-launch questions. Every one of them changes what the
 * bot does — trade length picks the chart it reads, autonomy decides who pulls
 * the trigger on a buy — so nothing here is asked just to fill in a profile.
 */

import { t, getLanguage } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("token");
  try { return fromUrl || localStorage.getItem("mt_token") || ""; } catch { return fromUrl || ""; }
})();
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);

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

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const locale = () => (getLanguage() === "tr" ? "tr-TR" : "en-US");
const usd = (n) => (n === null || n === undefined || Number.isNaN(n))
  ? "—"
  : "$" + Number(n).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signedUsd = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + usd(Math.abs(n));

const HORIZON_BY_TF = { "15m": "short", "1h": "medium", "1d": "long" };

function ago(iso) {
  if (!iso) return t("now.never");
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return t("time.s", { n: Math.round(s) });
  if (s < 5400) return t("time.m", { n: Math.round(s / 60) });
  return t("time.h", { n: Math.round(s / 3600) });
}

/* ------------------------------------------------------------------- now */

function renderNow(s) {
  if (!s) return;
  const card = $("nowCard");
  card.hidden = false;

  let title, state;
  if (s.halted || !s.running) { title = t("now.stopped"); state = "stopped"; }
  else if (s.last_error) { title = t("now.retrying"); state = "warn"; }
  else if (!s.market.is_open) { title = t("now.closed"); state = "idle"; }
  else { title = t("now.watching", { n: s.watchlist.length }); state = "live"; }

  card.dataset.state = state;
  $("nowTitle").textContent = title;
  $("nowSub").textContent = t("now.sub", {
    tf: t(`tf.${s.timeframe}`), ago: ago(s.last_scan_at),
  });

  const horizon = HORIZON_BY_TF[s.timeframe];
  $("nowMode").textContent = [
    t(`autonomy.${s.autonomy || "full"}`),
    horizon ? t(`horizon.${horizon}`) : null,
  ].filter(Boolean).join(" · ");

  renderFeed();
}

const hhmm = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

function renderFeed() {
  // The engine's own steps when there are any (live.js publishes them), else
  // the mentor's lines.
  const steps = window.mtSteps || [];
  if (steps.length) {
    $("nowFeed").innerHTML = steps.map((st) => `
      <li class="step-${esc(st.state)} k-${esc(st.kind)}"><span>${esc(hhmm(st.started_at))}</span>${esc(st.title)}${
        st.detail ? ` <em>⎿ ${esc(st.detail)}</em>` : ""}</li>`).join("");
    return;
  }
  const lines = (window.mtLines || []).slice(-3).reverse();
  $("nowFeed").innerHTML = lines.map((l) => `
    <li class="lvl-${esc(l.level)}"><span>${esc(l.clock || "")}</span>${esc(l.text)}</li>`).join("");
}

$("nowFeed").addEventListener("click", () => window.showView?.("live"));
$("nowTitle").addEventListener("click", () => window.showView?.("live"));

// "last look 12s ago" should tick, not jump every 20 seconds.
setInterval(() => {
  const s = window.mtState;
  if (s && !$("nowCard").hidden) {
    $("nowSub").textContent = t("now.sub", { tf: t(`tf.${s.timeframe}`), ago: ago(s.last_scan_at) });
  }
  tickExpiry();
}, 1000);

/* -------------------------------------------------------------- proposals */

function proposalRow(p, asking) {
  const line = t(asking ? "proposal.buy" : "proposal.idea", {
    qty: Number(p.qty).toLocaleString(locale(), { maximumFractionDigits: 4 }),
    symbol: p.symbol, price: usd(p.price),
  });
  const stops = p.stop_loss
    ? t("proposal.stops", { stop: usd(p.stop_loss), target: usd(p.take_profit) }) : "";
  return `
    <article class="proposal ${asking ? "asking" : "idea"}" data-id="${esc(p.id)}">
      <div class="proposal-main">
        <span class="ticker">${esc(p.symbol.slice(0, 2))}</span>
        <div>
          <b>${esc(line)}</b>
          <small>${esc(stops)}</small>
          <small class="proposal-why">${esc(p.reason || "")}</small>
        </div>
      </div>
      <div class="proposal-actions">
        ${asking ? `<span class="proposal-clock" data-expires="${esc(p.expires_at)}"></span>
          <button class="primary sm" data-approve="${esc(p.id)}">${esc(t("action.approve"))}</button>` : ""}
        <button class="ghost sm" data-skip="${esc(p.id)}">${esc(t("action.skip"))}</button>
      </div>
    </article>`;
}

function renderProposals(s) {
  const approvals = s.approvals || [];
  const ideas = s.suggestions || [];
  const box = $("proposalBox");
  if (!approvals.length && !ideas.length) { box.hidden = true; return; }

  box.hidden = false;
  box.classList.toggle("asking", approvals.length > 0);
  $("proposalTitle").textContent = t(approvals.length ? "proposals.approvals" : "proposals.suggestions");
  $("proposalList").innerHTML =
    approvals.map((p) => proposalRow(p, true)).join("")
    + ideas.map((p) => proposalRow(p, false)).join("");
  tickExpiry();
}

function tickExpiry() {
  document.querySelectorAll(".proposal-clock[data-expires]").forEach((el) => {
    const left = (new Date(el.dataset.expires) - Date.now()) / 60000;
    el.textContent = t("proposal.expires", { m: Math.max(0, Math.ceil(left)) });
  });
}

$("proposalList").addEventListener("click", async (e) => {
  const approve = e.target.closest("[data-approve]");
  const skip = e.target.closest("[data-skip]");
  if (!approve && !skip) return;
  const button = approve || skip;
  button.disabled = true;

  try {
    if (approve) {
      const result = await api("POST", `/api/proposals/${encodeURIComponent(approve.dataset.approve)}/approve`);
      window.showAlert?.({ tone: "good", title: result.message });
    } else {
      await api("POST", `/api/proposals/${encodeURIComponent(skip.dataset.skip)}/skip`);
    }
  } catch (err) {
    // A refused approval is information, not a crash: say exactly why.
    window.showAlert?.({ tone: "bad", title: err.message });
  } finally {
    window.refresh?.().catch(() => {});
    loadPerf(true);
  }
});

/* ------------------------------------------------------------ performance */

let perfAt = 0;
async function loadPerf(force = false) {
  if (!force && Date.now() - perfAt < 15000) return;
  perfAt = Date.now();
  try {
    renderPerf(await api("GET", "/api/performance"));
  } catch { /* the rest of home still works without it */ }
}

function renderPerf(p) {
  const card = $("perfCard");
  card.hidden = false;
  const money = t(p.practice ? "perf.practice" : "perf.real");

  if (!p.trades && !p.unrealised) {
    card.dataset.tone = "none";
    $("perfLabel").textContent = money;
    $("perfFigure").textContent = t("perf.none");
    $("perfSub").textContent = t("perf.noneBody");
    return;
  }

  card.dataset.tone = p.total > 0 ? "up" : p.total < 0 ? "down" : "none";
  $("perfLabel").textContent = `${t(p.total < 0 ? "perf.lost" : "perf.made")} · ${money}`;
  $("perfFigure").textContent = signedUsd(p.total);

  const parts = [t("perf.sub", { equity: usd(p.equity), trades: p.trades, wins: p.wins })];
  if (p.starting_balance) parts.push(t("perf.start", { start: usd(p.starting_balance) }));
  if (p.unrealised) parts.push(t("perf.open", { amount: signedUsd(p.unrealised) }));
  $("perfSub").textContent = parts.join(" · ");
}

/* ------------------------------------------------------------- onboarding */

let profile = null;
const answers = { market: "unknown", trading_horizon: "unknown", autonomy: "unknown", technical_level: "beginner" };
// Only answers the owner actually gave are highlighted — a default is not
// a choice, and showing "Not sure" pre-selected reads as if they picked it.
const touched = new Set();

const STEPS = [
  {
    field: "market", q: "ob.q0",
    options: [
      ["us", "ob.us", "ob.usHint"],
      ["europe", "ob.europe", "ob.europeHint"],
      ["both", "ob.both", "ob.bothHint"],
    ],
  },
  {
    field: "trading_horizon", q: "ob.q1",
    options: [
      ["short", "ob.short", "ob.shortHint"],
      ["medium", "ob.medium", "ob.mediumHint"],
      ["long", "ob.long", "ob.longHint"],
      ["unknown", "ob.unsure", "ob.unsureHorizon"],
    ],
  },
  {
    field: "autonomy", q: "ob.q2",
    options: [
      ["full", "autonomy.full", "ob.fullHint"],
      ["semi", "autonomy.semi", "ob.semiHint"],
      ["manual", "autonomy.manual", "ob.manualHint"],
      ["unknown", "ob.unsure", "ob.unsureAutonomy"],
    ],
  },
  {
    field: "technical_level", q: "ob.q3",
    options: [
      ["beginner", "a.beginner", "ob.beginnerHint"],
      ["intermediate", "a.intermediate", "ob.intermediateHint"],
      ["advanced", "a.advanced", "ob.advancedHint"],
    ],
  },
];

let step = -1;

function openOnboarding() {
  step = -1;
  touched.clear();
  if (profile && profile.onboarded) {
    // Asking again: start from what they answered last time.
    for (const field of Object.keys(answers)) {
      if (profile[field] && profile[field] !== "unknown") {
        answers[field] = profile[field];
        touched.add(field);
      }
    }
  }
  $("onboard").hidden = false;
  drawOnboarding();
}

function closeOnboarding() {
  $("onboard").hidden = true;
}

function drawOnboarding() {
  const body = $("onboardBody");
  $("onboardBar").style.width = `${Math.max(0, (step + 1) / (STEPS.length + 1)) * 100}%`;

  if (step === -1) {
    body.innerHTML = `
      <h2>${esc(t("ob.hello"))}</h2>
      <p class="onboard-lead">${esc(t("ob.helloBody"))}</p>
      <div class="onboard-actions">
        <button class="primary" data-ob="start">${esc(t("ob.start"))}</button>
        <button class="ghost" data-ob="later">${esc(t("ob.later"))}</button>
      </div>`;
    return;
  }

  if (step < STEPS.length) {
    const s = STEPS[step];
    body.innerHTML = `
      <span class="onboard-step">${esc(t("ob.step", { n: step + 1 }))}</span>
      <h2>${esc(t(s.q))}</h2>
      <div class="onboard-options">
        ${s.options.map(([value, label, hint]) => `
          <button class="onboard-option ${touched.has(s.field) && answers[s.field] === value ? "on" : ""}"
                  data-ob-field="${s.field}" data-ob-value="${value}">
            <b>${esc(t(label))}</b><span>${esc(t(hint))}</span>
          </button>`).join("")}
      </div>
      ${step > 0 ? `<button class="ghost sm onboard-back" data-ob="back">${esc(t("action.back"))}</button>` : ""}`;
    return;
  }

  // Say back what was understood, in terms of what the bot will now do.
  const mode = (window.mtState && window.mtState.mode) || "paper";
  const horizon = answers.trading_horizon === "unknown" ? "short" : answers.trading_horizon;
  const tf = { short: "15m", medium: "1h", long: "1d" }[horizon];
  const autonomy = answers.autonomy !== "unknown"
    ? answers.autonomy : (mode === "live" ? "semi" : "full");
  const market = answers.market === "unknown" ? null : answers.market;
  const sentences = [
    market ? t("ob.sumMarket", { market: t(`market.${market}`) }) : null,
    t("ob.sumHorizon", { tf: t(`tf.${tf}`).toLowerCase() }),
    t({ full: "ob.sumFull", semi: "ob.sumSemi", manual: "ob.sumManual" }[autonomy]),
    t(mode === "live" ? "ob.sumReal" : "ob.sumPractice"),
  ];
  body.innerHTML = `
    <h2>${esc(t("ob.doneTitle"))}</h2>
    <ul class="onboard-summary">${sentences.filter(Boolean).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <div class="onboard-actions">
      <button class="primary" data-ob="finish">${esc(t("ob.go"))}</button>
      <button class="ghost" data-ob="back">${esc(t("action.back"))}</button>
    </div>`;
}

$("onboard").addEventListener("click", async (e) => {
  const option = e.target.closest("[data-ob-field]");
  if (option) {
    answers[option.dataset.obField] = option.dataset.obValue;
    touched.add(option.dataset.obField);
    step += 1;
    drawOnboarding();
    return;
  }
  const action = e.target.closest("[data-ob]")?.dataset.ob;
  if (!action) return;

  if (action === "start") { step = 0; drawOnboarding(); }
  else if (action === "back") { step = Math.max(-1, step - 1); drawOnboarding(); }
  else if (action === "later") {
    // "Later" means stop asking at every launch; Settings can ask again.
    await saveProfile({ onboarded: true });
    closeOnboarding();
  } else if (action === "finish") {
    await saveProfile({ ...answers, onboarded: true });
    closeOnboarding();
    window.refresh?.().catch(() => {});
  }
});

async function saveProfile(changes) {
  try {
    const data = await api("PATCH", "/api/profile", changes);
    profile = data.profile;
    renderTradingSettings();
  } catch (err) {
    window.showAlert?.({ tone: "bad", title: err.message });
  }
}

/* --------------------------------------------------------------- settings */

const TRADING_FIELDS = [
  ["market", "sm.market", [["us", "ob.us"], ["europe", "ob.europe"], ["both", "ob.both"]]],
  ["trading_horizon", "settings.horizon", [["short", "horizon.short"], ["medium", "horizon.medium"], ["long", "horizon.long"]]],
  ["autonomy", "settings.autonomy", [["full", "autonomy.full"], ["semi", "autonomy.semi"], ["manual", "autonomy.manual"]]],
  ["small_account", "sm.small", [["true", "sm.smallOn"], ["false", "sm.smallOff"]], "sm.smallHint"],
];

function renderTradingSettings() {
  const host = $("sTrading");
  if (!host || !profile) return;
  const live = window.mtState || {};
  const small = live.small_account ?? profile.small_account;
  const current = {
    market: profile.market,
    trading_horizon: HORIZON_BY_TF[live.timeframe] || profile.trading_horizon,
    autonomy: live.autonomy || profile.autonomy,
    small_account: small === undefined ? undefined : String(Boolean(small)),
  };
  host.innerHTML = TRADING_FIELDS.map(([field, label, options, hint]) => `
    <div class="field-block">
      <label>${esc(t(label))}</label>
      <div class="chips tagset">
        ${options.map(([value, key]) => `
          <button class="chip pickable ${current[field] === value ? "on" : ""}"
                  data-tfield="${field}" data-tvalue="${value}">${esc(t(key))}</button>`).join("")}
      </div>
      ${hint ? `<p class="note faint">${esc(t(hint))}</p>` : ""}
    </div>`).join("")
    + `<div class="actions"><button class="ghost" data-ob-redo>${esc(t("settings.redoSetup"))}</button></div>`;
}

document.addEventListener("click", async (e) => {
  const chip = e.target.closest("[data-tfield]");
  if (chip) {
    const field = chip.dataset.tfield;
    // A switch is a real true/false on the server, not the text "false".
    const value = field === "small_account" ? chip.dataset.tvalue === "true" : chip.dataset.tvalue;
    await saveProfile({ [field]: value });
    window.refresh?.().catch(() => {});
    return;
  }
  if (e.target.closest("[data-ob-redo]") || e.target.closest("#nowMode")) openOnboarding();
});

/* ----------------------------------------------------------------- wiring */

window.addEventListener("mt:status", (e) => {
  renderNow(e.detail);
  renderProposals(e.detail);
  renderTradingSettings();
  loadPerf();
});

window.addEventListener("mt:line", () => { if (!$("nowCard").hidden) renderFeed(); });
window.addEventListener("mt:steps", () => { if (!$("nowCard").hidden) renderFeed(); });

window.addEventListener("mt:ws", (e) => {
  const msg = e.detail;
  if (msg.type === "approval_needed") {
    const p = msg.proposal;
    window.showAlert?.({
      tone: "info", symbol: p.symbol, title: t("proposals.approvals"),
      body: t("proposal.buy", { qty: p.qty, symbol: p.symbol, price: usd(p.price) }),
    });
    window.refresh?.().catch(() => {});
  } else if (["proposal_resolved", "proposal_expired", "suggestion"].includes(msg.type)) {
    window.refresh?.().catch(() => {});
  } else if (msg.type === "trade_closed" || msg.type === "trade_opened") {
    loadPerf(true);
  }
});

window.addEventListener("mt:lang", () => {
  const s = window.mtState;
  if (s) { renderNow(s); renderProposals(s); }
  renderTradingSettings();
  loadPerf(true);
  if (!$("onboard").hidden) drawOnboarding();
});

(async () => {
  // chart.js may already have drawn a status before this module ran.
  if (window.mtState) {
    renderNow(window.mtState);
    renderProposals(window.mtState);
  }
  loadPerf(true);
  try {
    profile = (await api("GET", "/api/profile")).profile;
    renderTradingSettings();
    if (!profile.onboarded) openOnboarding();
  } catch { /* no profile store: skip onboarding rather than block the app */ }
})();
