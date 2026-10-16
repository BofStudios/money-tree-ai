/* Modes, readiness and memory (desktop 6.0).
 *
 *   Modes tab   every way the bot can run, as a few big cards: speed, style,
 *               who decides, money, smart features.
 *   Readiness   "is it trading, and if not why" with the button that fixes
 *               it, on Home and on Modes. Real money still arms only when the
 *               owner presses Arm, after every start of the app.
 *   Memory      what the bot learned and how far it grew (Brain → Memory).
 */

import { t } from "/i18n.js";

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
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

let view = "home";
let modes = null;
let ready = null;
let memory = null;
let busy = false;

/* ------------------------------------------------------------- readiness */

const STATE_MARK = { ok: "✓", warn: "!", bad: "✕", info: "i" };

function readyCard(r, compact) {
  if (!r) return "";
  const word = t(`ready.${r.verdict}`);
  const fix = r.fix ? `<button class="${r.fix === "arm" ? "arm-big" : "primary"}" data-fix="${esc(r.fix)}">${esc(t(`ready.fix.${r.fix}`))}</button>` : "";
  const missed = r.missed_total ? `
      <div class="rd-missed">
        <span>${esc(t("ready.missed", { n: r.missed_total }))}</span>
        <ul>${r.missed.map((m) => `<li><b>${m.count}×</b> ${esc(m.title)}${m.symbol ? ` <em>${esc(m.symbol)}</em>` : ""}${m.detail ? `<small>${esc(m.detail)}</small>` : ""}</li>`).join("")}</ul>
      </div>` : "";
  const checks = compact ? "" : `
      <details class="rd-all" ${r.verdict === "watching" ? "open" : ""}>
        <summary>${esc(t("ready.all"))}</summary>
        <ul class="rd-checks">${r.checks.map((c) => `
          <li class="rd-${c.state}"><i>${STATE_MARK[c.state] || "·"}</i>
            <div><b>${esc(c.title)}</b>${c.detail ? `<small>${esc(c.detail)}</small>` : ""}</div>
            ${c.fix && c.state !== "ok" && c.state !== "info" ? `<button class="ghost sm" data-fix="${esc(c.fix)}">${esc(t(`ready.fix.${c.fix}`))}</button>` : ""}
          </li>`).join("")}</ul>
      </details>`;
  return `
    <section class="ready-card rd-${esc(r.verdict)}">
      <div class="rd-head">
        <span class="rd-led"></span>
        <div class="rd-text"><span class="rd-word">${esc(word)}</span><b>${esc(r.headline)}</b></div>
        ${fix}
      </div>
      ${missed}${checks}
      ${compact && memory ? levelStrip(memory) : ""}
    </section>`;
}

function levelStrip(m) {
  const pct = Math.round((m.progress || 0) * 100);
  return `<button class="lvl-strip" data-open-memory>
      <span class="lvl-badge">${esc(t("mem.level", { n: m.level }))}</span>
      <span class="lvl-bar"><i style="width:${pct}%"></i></span>
      <span class="lvl-days">${esc(t("mem.days", { n: Math.max(m.days_open || 1, ((m.facts.find((f) => f.key === "age") || {}).value || 0)) }))}</span>
    </button>`;
}

function renderReady() {
  if ($("homeReady")) $("homeReady").innerHTML = readyCard(ready, true);
  if ($("modesReady")) $("modesReady").innerHTML = readyCard(ready, false);
  const pill = $("readyPill");
  if (pill && ready) {
    pill.hidden = false;
    pill.className = `ready-pill rd-${ready.verdict}`;
    pill.textContent = t(`ready.${ready.verdict}`);
  }
}

async function loadReady() {
  try { ready = await api("GET", "/api/readiness"); renderReady(); } catch { /* the next poll tries again */ }
}

/* -------------------------------------------------------------- scorecard */

let score = null;

function pct(v) { return v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`; }

function scoreCard(s) {
  if (!s) return "";
  const tone = s.verdict === "ahead" ? "up" : s.verdict === "behind" ? "down" : "";
  return `
    <section class="score-card sc-${esc(s.verdict || "none")}">
      <div class="sc-head"><span class="sc-word">${esc(t("score.title"))}</span><b>${esc(s.headline)}</b></div>
      ${s.bot_pct === null ? "" : `
      <div class="sc-vs">
        <div><span>${esc(t("score.bot"))}</span><b class="${tone}">${esc(pct(s.bot_pct))}</b><small>$${Number(s.start_equity).toFixed(2)} → $${Number(s.equity).toFixed(2)}</small></div>
        <i>vs</i>
        <div><span>${esc(t("score.spy"))}</span><b>${esc(pct(s.spy_pct))}</b><small>${s.spy_value ? `$${Number(s.start_equity).toFixed(2)} → $${Number(s.spy_value).toFixed(2)}` : ""}</small></div>
      </div>`}
      <p class="note faint">${esc(t("score.trades", { n: s.trades, w: s.win_rate, p: `${s.realised >= 0 ? "+" : ""}$${Number(s.realised).toFixed(2)}` }))} · ${esc(s.note)}</p>
    </section>`;
}

async function loadScore() {
  try { score = await api("GET", "/api/scorecard"); } catch { return; }
  if ($("homeScore")) $("homeScore").innerHTML = scoreCard(score);
}

/* ------------------------------------------------------------------ modes */

function cardRow(group, options, active, extra = {}) {
  return `<div class="mode-row">${options.map((o) => `
    <button class="mode-card ${o === active ? "on" : ""} ${group}-${o}" data-pick="${group}" data-value="${o}">
      <span class="mc-dot"></span>
      <b>${esc(t(`modes.${group}.${o}`))}</b>
      <small>${esc(t(`modes.${group}.${o}Body`))}</small>
      ${extra[o] || ""}
    </button>`).join("")}</div>`;
}

function renderModes() {
  const body = $("modesBody");
  if (!body || !modes) return;
  const s = window.mtState || {};
  const live = (s.broker || modes.money.broker) === "alpaca_live";
  const armed = !!(s.risk ? s.risk.armed : modes.money.armed);
  const moneyActive = live ? "real" : "practice";
  const moneyExtra = {
    real: live
      ? `<span class="mc-state ${armed ? "armed" : ""}">${esc(t(armed ? "modes.money.armed" : "modes.money.notArmed"))}</span>`
      : "",
  };
  const switches = Object.entries(modes.switches || {}).map(([k, on]) => `
    <label class="gate"><input type="checkbox" data-switch="${esc(k)}" ${on ? "checked" : ""}>
      <span class="switch"></span><span><b>${esc(t(`modes.sw.${k}`))}</b><small>${esc(t(`modes.sw.${k}Hint`))}</small></span></label>`).join("");
  body.innerHTML = `
    <section class="mode-block">
      <h2>${esc(t("modes.money"))}</h2>
      ${cardRow("money", ["practice", "real"], moneyActive, moneyExtra)}
      <div class="mode-actions">
        ${live ? `<button class="${armed ? "ghost" : "arm-big"}" data-arm="${armed ? "off" : "on"}">${esc(t(armed ? "modes.money.disarm" : "modes.money.arm"))}</button>` : ""}
      </div>
    </section>
    <section class="mode-block">
      <h2>${esc(t("modes.speed"))}</h2>
      ${cardRow("speed", ["eco", "normal", "ultra"], modes.speed)}
    </section>
    <section class="mode-block">
      <h2>${esc(t("modes.style"))}</h2>
      ${cardRow("style", ["careful", "balanced", "bold"], modes.style)}
      ${modes.style === "custom" ? `<p class="note faint">${esc(t("modes.style.custom"))}</p>` : ""}
    </section>
    <section class="mode-block">
      <h2>${esc(t("modes.who"))}</h2>
      ${cardRow("who", ["full", "semi", "manual"], modes.autonomy)}
    </section>
    <section class="mode-block">
      <h2>${esc(t("modes.smart"))}</h2>
      <div class="gate-grid">${switches}</div>
    </section>
    <p class="note faint legal-note">${esc(t("settings.legal"))}
      <a href="/guide.html" target="_blank" rel="noopener">${esc(t("modes.guide"))} ↗</a></p>`;
}

async function loadModes() {
  try { modes = await api("GET", "/api/modes"); renderModes(); } catch { /* shown on the next try */ }
}

async function change(body) {
  if (busy) return;
  busy = true;
  try {
    modes = await api("POST", "/api/modes", body);
    renderModes();
    window.showAlert?.({ tone: "good", title: t("modes.saved") });
  } catch (err) {
    window.showAlert?.({ tone: "bad", title: err.message });
  } finally {
    busy = false;
    loadReady();
  }
}

async function arm(on) {
  try {
    if (on) {
      if (!confirm(t("arm.confirm"))) return;
      await api("POST", "/api/arm", { confirm: true });
    } else {
      await api("POST", "/api/disarm");
    }
  } catch (err) {
    window.showAlert?.({ tone: "bad", title: err.message });
  }
  loadReady();
  loadModes();
}

async function fix(what) {
  if (what === "arm") return arm(true);
  if (what === "start") {
    try { await api("POST", "/api/engine/start"); } catch (err) { window.showAlert?.({ tone: "bad", title: err.message }); }
    return loadReady();
  }
  window.showView?.(what === "money" ? "money" : what);
}

/* ----------------------------------------------------------------- memory */

const KIND_ICON = { promotion: "▲", rule: "◆", lesson: "✦", buy: "＋", sell: "−", level: "★", arm: "●" };

function fmt(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  return Number(n || 0).toLocaleString();
}

function when(epoch) {
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function memoryHtml(m) {
  if (!m) return `<div class="fl-card"><p class="note">…</p></div>`;
  const pct = Math.round((m.progress || 0) * 100);
  const ring = `conic-gradient(var(--accent) ${pct * 3.6}deg, rgba(255,214,10,0.12) 0)`;
  const facts = m.facts.map((f) => `
      <div class="mem-fact"><b>${esc(fmt(f.value))}</b><span>${esc(f.label)}</span></div>`).join("");
  const growth = m.growth.length ? m.growth.map((e) => `
      <li class="g-${esc(e.kind)}"><i>${KIND_ICON[e.kind] || "·"}</i>
        <div><b>${esc(e.title)}</b>${e.detail ? `<small>${esc(e.detail)}</small>` : ""}</div>
        <time>${esc(when(e.at))}</time></li>`).join("")
    : `<li class="empty">${esc(t("mem.noGrowth"))}</li>`;
  const lessons = m.news_lessons.length ? m.news_lessons.map((l) => {
    const tone = l.trust > 1.02 ? "up" : l.trust < 0.98 ? "down" : "";
    return `<li><b>${esc(l.label)}</b>
        <span>${esc(t("mem.cases", { n: l.n }))} · ${esc(t("mem.hit", { x: `${Math.round(l.hit * 100)}%` }))} · ${esc(t("mem.avg", { x: `${l.avg >= 0 ? "+" : ""}${l.avg.toFixed(2)}%` }))}</span>
        <em class="${tone}">${esc(t("mem.trust", { x: l.trust.toFixed(2) }))}</em></li>`;
  }).join("") : `<li class="empty">${esc(t("mem.newsEmpty"))}</li>`;
  return `
    <section class="mem-hero fl-card glow">
      <div class="mem-ring" style="background:${ring}"><div><b>${m.level}</b><span>${esc(t("mem.level", { n: "" }).trim())}</span></div></div>
      <div class="mem-hero-text">
        <h3>${esc(t("mem.level", { n: m.level }))}</h3>
        <p>${esc(t("mem.toNext", { x: m.into, y: m.need, n: m.level + 1 }))}</p>
        <p class="note faint">${esc(t("mem.since", { d: new Date(m.first_day * 1000).toLocaleDateString() }))} · ${esc(t("mem.subtitle"))}</p>
      </div>
    </section>
    <h2 class="mem-h">${esc(t("mem.facts"))}</h2>
    <div class="mem-facts">${facts}</div>
    <h2 class="mem-h">${esc(t("mem.news"))}</h2>
    <p class="note faint">${esc(t("mem.newsHint"))}${m.news_waiting ? " " + esc(t("mem.newsWaiting", { n: m.news_waiting })) : ""}</p>
    <ul class="mem-lessons">${lessons}</ul>
    <h2 class="mem-h">${esc(t("mem.growth"))}</h2>
    <ul class="mem-growth">${growth}</ul>`;
}

async function loadMemory() {
  try { memory = await api("GET", "/api/memory"); } catch { return; }
  const host = $("memView");
  if (host) host.innerHTML = memoryHtml(memory);
  renderReady();
}
window.mtRenderMemory = () => {
  const host = $("memView");
  if (host) host.innerHTML = memoryHtml(memory);
  loadMemory();
};

/* ----------------------------------------------------------------- events */

document.addEventListener("click", (e) => {
  const b = e.target.closest("button, [data-open-memory]");
  if (!b) return;
  if (b.dataset.fix) { fix(b.dataset.fix); return; }
  if (b.dataset.arm) { arm(b.dataset.arm === "on"); return; }
  if (b.hasAttribute("data-open-memory")) { window.mtOpenBrainTab?.("memory"); return; }
  const group = b.dataset.pick;
  const value = b.dataset.value;
  if (!group || !modes) return;
  if (group === "speed") {
    if (value === "ultra") {
      if (modes.speed === "ultra") { window.showAlert?.({ tone: "good", title: t("modes.ultraOn") }); return; }
      window.mtUltra?.warn(() => loadModes());
      return;
    }
    if (value !== modes.speed) change({ speed: value });
  } else if (group === "style") {
    if (value !== modes.style) change({ style: value });
  } else if (group === "who") {
    if (value === modes.autonomy) return;
    api("PATCH", "/api/profile", { autonomy: value })
      .then(() => { window.showAlert?.({ tone: "good", title: t("modes.saved") }); loadModes(); loadReady(); })
      .catch((err) => window.showAlert?.({ tone: "bad", title: err.message }));
  } else if (group === "money") {
    const live = (window.mtState || {}).broker === "alpaca_live";
    if (value === "real" && !live) {
      const go = document.querySelector("[data-go-real]");
      if (go) go.click(); else window.showView?.("settings");
    } else if (value === "practice" && live) {
      window.showView?.("settings");
    }
  }
});

document.addEventListener("change", (e) => {
  const box = e.target.closest("input[data-switch]");
  if (box) change({ [box.dataset.switch]: box.checked });
});

window.addEventListener("mt:view", (e) => {
  view = e.detail;
  if (view === "modes") { loadModes(); loadReady(); }
  if (view === "home") { loadReady(); loadScore(); }
  if (view === "settings") api("GET", "/api/modes").then((m) => { if ($("dataHomePath")) $("dataHomePath").textContent = m.home; }).catch(() => {});
});
let lastStatus = 0;
window.addEventListener("mt:status", () => {
  if (Date.now() - lastStatus < 4000) return;
  lastStatus = Date.now();
  if (view === "home" || view === "modes") loadReady();
  if (view === "modes" && !busy) loadModes();
});
window.addEventListener("mt:lang", () => { renderReady(); renderModes(); const h = $("memView"); if (h) h.innerHTML = memoryHtml(memory); });

setInterval(() => { if (!document.hidden) loadReady(); }, 15000);
loadReady();
loadMemory();
loadScore();
setInterval(() => { if (!document.hidden && view === "home") loadScore(); }, 300000);
setInterval(() => { if (!document.hidden) loadMemory(); }, 120000);
