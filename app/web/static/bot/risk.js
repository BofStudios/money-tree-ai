/* The owner's limits and the pace (B3.1–B3.4). One component, drawn in the
 * Bot drawer and in Settings. Empty field = no limit (null to the server).
 * The server clamps; the field then shows the server's value and says why.
 * Loosening a limit on a real account needs a second, inline click (409).
 * Every sentence's amount is computed from the typed value, nothing else.
 */

import { $, T, esc, money, pct, api, lang } from "./util.js";
import { store, loadSnap } from "./store.js";

// The budget is the big amount field at the top of the console (amount.js).
const FIELDS = [
  { id: "per_trade_pct", min: 0.25, max: 5, step: 0.25, unit: "%" },
  { id: "daily_loss", min: 1, step: 1, unit: "$" },
  { id: "max_positions", min: 1, max: 5, step: 1, unit: "" },
];
const PACES = ["calm", "balanced", "aggressive"];
const hosts = () => [$("mbRiskDrawer"), $("mbRiskSettings")].filter(Boolean);

let draft = null;        // values being typed, per field
let msg = null;          // {tone, text}
let pending = null;      // a body waiting for the owner's second click (409)
let paces = null;
let busy = false;

const equity = () => (store.snap && store.snap.tiles && store.snap.tiles.capital && store.snap.tiles.capital.equity) || 0;
const num = (v) => (v === "" || v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

function current() {
  const r = (store.snap && store.snap.risk) || {};
  return { budget: r.budget ?? null, ...Object.fromEntries(FIELDS.map((f) => [f.id, r[f.id] ?? null])) };
}

function say(id, v, vals) {
  const base = vals.budget ?? equity();
  if (id === "per_trade_pct") return v == null ? T("risk.say.perNone") : T("risk.say.per", { v: money((base * v) / 100) });
  if (id === "daily_loss") return v == null ? T("risk.say.lossNone") : T("risk.say.loss", { v: money(v) });
  return v == null ? T("risk.say.posNone") : T("risk.say.pos", { n: v });
}

function field(f, vals) {
  const v = vals[f.id];
  const max = f.max ?? (f.id === "daily_loss" ? Math.max(1, Math.round((vals.budget ?? equity()) * 0.2)) : Math.max(1, Math.round(equity())));
  return `<div class="mb-rf" data-field="${f.id}">
    <label for="rf-${f.id}-%H">${esc(T(`risk.f.${f.id}`))}</label>
    <div class="mb-rf-row">
      <input class="mb-rf-num num" id="rf-${f.id}-%H" type="number" inputmode="decimal" min="${f.min}" max="${max}" step="${f.step}"
        value="${v ?? ""}" placeholder="${esc(T("risk.none"))}" data-k="${f.id}">
      <span class="mb-dim">${f.unit}</span>
      <input class="mb-rf-range" type="range" min="${f.min}" max="${max}" step="${f.step}" value="${v ?? max}" ${v == null ? "data-off" : ""} data-k="${f.id}" aria-label="${esc(T(`risk.f.${f.id}`))}">
    </div>
    <p class="mb-rf-say">${esc(say(f.id, v, vals))}</p>
  </div>`;
}

function usage() {
  const r = (store.snap && store.snap.risk) || {};
  if (r.paused) return `<p class="mb-rf-paused">${esc(r.paused)}</p>`;
  if (!r.daily_loss) return "";
  const used = Math.min(100, (100 * (r.daily_loss_used || 0)) / r.daily_loss);
  return `<div class="mb-rf-use"><span>${esc(T("risk.used", { u: money(r.daily_loss_used || 0), l: money(r.daily_loss) }))}</span>
    <i aria-hidden="true"><b style="width:${used.toFixed(1)}%"></b></i></div>`;
}

function paceRow(p, on) {
  const pr = p.proof || {};
  const line = pr.state === "untested" || pr.state === "stale" || !pr.trades
    ? T("risk.pace.noData")
    : T("risk.pace.lab", { d: pr.days, n: pr.trades, p: pct(pr.per_trade_pct), f: pr.profit_factor ?? "—" });
  return `<button class="mb-pace${on ? " on" : ""}" type="button" role="radio" aria-checked="${on}" data-pace="${esc(p.id)}">
    <b>${esc(T(`risk.pace.${p.id}`))}</b>
    <span class="mb-dim">${esc(line)}</span>
    ${pr.state === "lost" ? `<em class="mb-badge">${esc(T("risk.pace.lost"))}</em>` : pr.state === "passed" ? `<em class="mb-badge ok">${esc(T("risk.pace.passed"))}</em>` : ""}
  </button>`;
}

/* The AI planner (M3): it may only keep, shrink or skip a planned trade, never
   start one or loosen a limit. Off by default; its advice comes from the server. */
function planner() {
  const r = (store.snap && store.snap.risk) || {};
  if (r.planner === undefined) return "";
  const on = !!r.planner;
  const advice = Array.isArray(r.advice) ? r.advice : [];
  const until = (ms) => (ms ? new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");
  return `<h3>${esc(T("planner.title"))}</h3>
    <button class="mb-switch" type="button" role="switch" aria-checked="${on}" data-planner="${on ? "off" : "on"}" ${busy ? "disabled" : ""}>
      <i aria-hidden="true"></i><span>${esc(T(on ? "planner.on" : "planner.off"))}</span></button>
    <p class="mb-rf-say">${esc(T("planner.what"))}${on && r.planner_calls_left != null ? " " + esc(T("planner.left", { n: r.planner_calls_left })) : ""}</p>
    ${on ? (advice.length ? `<ul class="mb-advice">${advice.map((a) => `<li data-act="${esc(a.action)}"><b class="mono">${esc(a.symbol)}</b>
      <em>${esc(T(`planner.act.${["keep", "shrink", "skip"].includes(a.action) ? a.action : "keep"}`))}</em>
      <span>${esc(a.why || "")}</span>${a.until ? `<small class="mb-dim">${esc(T("planner.until", { t: until(a.until) }))}</small>` : ""}</li>`).join("")}</ul>`
      : `<p class="mb-dim">${esc(T("planner.none"))}</p>`) : ""}`;
}

function html(h) {
  if (!store.snap) return `<p class="mb-dim">${esc(T("err.load"))}</p>`;
  const vals = { ...current(), ...(draft || {}) };
  // 12.0: no pace picker; the bot always runs at full power (owner's decision).
  return `<div class="mb-risk">
    <h3>${esc(T("risk.title"))}</h3>
    <form class="mb-rf-grid" data-risk-form novalidate>${FIELDS.map((f) => field(f, vals)).join("").replaceAll("%H", h)}
      <div class="mb-rf-actions">
        <button class="mb-btn mb-ok" type="submit" ${busy || !draft ? "disabled" : ""}>${esc(T("risk.save"))}</button>
        ${draft ? `<button class="mb-btn" type="button" data-risk-undo>${esc(T("risk.undo"))}</button>` : ""}
        ${pending ? `<button class="mb-btn mb-warnbtn" type="button" data-risk-confirm>${esc(T("risk.confirm"))}</button>` : ""}
      </div>
    </form>
    ${msg ? `<p class="mb-note ${msg.tone === "ok" ? "ok" : ""}">${esc(msg.text)}</p>` : ""}
    ${usage()}
    ${planner()}
  </div>`;
}

function draw() {
  hosts().forEach((h, i) => {
    if (h.contains(document.activeElement) && document.activeElement.matches("input")) {
      // Typing: only refresh the sentences and buttons, not the inputs.
      const vals = { ...current(), ...(draft || {}) };
      h.querySelectorAll(".mb-rf").forEach((el) => { el.querySelector(".mb-rf-say").textContent = say(el.dataset.field, vals[el.dataset.field], vals); });
      const save = h.querySelector('[type="submit"]'); if (save) save.disabled = busy || !draft;
      return;
    }
    h.innerHTML = html(`h${i}`);
  });
}

async function loadPaces() {
  try { paces = await api("GET", `/api/bot/paces?lang=${lang() === "tr" ? "tr" : "en"}`); } catch { paces = null; }
  draw();
}

function describeClamp(c) {
  if (typeof c === "string") return T("risk.clamped", { f: T(`risk.f.${c}`) });
  if (c && c.field) return T("risk.clampedTo", { f: T(`risk.f.${c.field}`), v: c.value ?? c.to ?? "" });
  return T("risk.clamped", { f: "" });
}

async function send(path, body) {
  busy = true; draw();
  try {
    const res = await api("POST", path, body);
    pending = null;
    const clamped = Array.isArray(res.clamped) ? res.clamped : [];
    msg = clamped.length ? { tone: "warn", text: clamped.map(describeClamp).join(" ") } : { tone: "ok", text: T("risk.saved") };   // clamped = field names
    draft = null;
    if (res.proof && paces) loadPaces();
  } catch (err) {
    // A real account refuses to loosen without a second click: offer it inline.
    if (err.status === 409) { pending = { path, body: { ...body, confirm: true } }; msg = { tone: "warn", text: err.message }; }
    else msg = { tone: "warn", text: T("risk.failed", { why: err.message }) };
  }
  busy = false;
  await loadSnap();
  draw();
}

function onInput(e) {
  const k = e.target.dataset.k;
  if (!k) return;
  draft = draft || {};
  const v = num(e.target.value);
  draft[k] = v;
  const box = e.target.closest(".mb-rf");
  if (e.target.type === "range") { box.querySelector(".mb-rf-num").value = v ?? ""; e.target.removeAttribute("data-off"); }
  else if (v != null) box.querySelector(".mb-rf-range").value = v;
  msg = null; pending = null;
  draw();
}

function onClick(e) {
  if (e.target.closest("[data-risk-undo]")) { draft = null; msg = null; pending = null; hosts().forEach((h) => { h.innerHTML = ""; }); draw(); return; }
  if (e.target.closest("[data-risk-confirm]") && pending) { send(pending.path, pending.body); return; }
  const pl = e.target.closest("[data-planner]");
  if (pl && !busy) { msg = null; send("/api/bot/planner", { on: pl.dataset.planner === "on" }); return; }
  const p = e.target.closest("[data-pace]");
  if (p && !busy) { msg = null; send("/api/bot/pace", { pace: p.dataset.pace }); }
}

function onSubmit(e) {
  if (!e.target.matches("[data-risk-form]")) return;
  e.preventDefault();
  if (!draft || busy) return;
  send("/api/bot/risk", { ...draft });
}

let wired = new WeakSet();
function wire() {
  hosts().forEach((h) => {
    if (wired.has(h)) return;
    wired.add(h);
    h.addEventListener("input", onInput);
    h.addEventListener("click", onClick);
    h.addEventListener("submit", onSubmit);
  });
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("all")) { wire(); draw(); }
});
window.addEventListener("mt:view", (e) => { if (e.detail === "settings") { wire(); draw(); if (!paces) loadPaces(); } });
window.addEventListener("mt:lang", () => { paces = null; loadPaces(); });

/* The drawer on the Bot view. */
export function toggleDrawer(open) {
  const d = $("mbRiskDrawer");
  if (!d) return;
  const show = open ?? d.hidden;
  d.hidden = !show;
  $("mbRiskOpen")?.setAttribute("aria-expanded", String(show));
  if (show) { wire(); draw(); if (!paces) loadPaces(); d.querySelector("input")?.focus(); }
}
$("mbRiskOpen")?.addEventListener("click", () => {
  if (document.body.dataset.group !== "bot" && window.showView) window.showView("bot");
  toggleDrawer();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("mbRiskDrawer") && !$("mbRiskDrawer").hidden) toggleDrawer(false); });
