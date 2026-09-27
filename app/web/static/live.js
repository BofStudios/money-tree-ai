/* The Live tab: every step the engine takes, as it takes it.
 *
 * Each step is opened on the server before the work starts and closed when it
 * ends, so a spinner here means a real call is in flight right now — nothing
 * is animated for show. Steps arrive over the socket (chart.js owns it and
 * re-broadcasts every message as mt:ws); a page that just opened gets the
 * history from /api/steps.
 *
 * Newest at the bottom, like a terminal. The view sticks to the bottom while
 * you are there and stays put when you scroll up to read.
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

const CAP = 300;
const LINES_SHOWN = 6;
const TRADE_KINDS = new Set(["order", "sell", "trail", "approval", "ai"]);

const steps = new Map();          // id -> step
const expanded = new Set();       // ids whose long result is unfolded
let filter = "all";
let look = {};                    // running / focus / next_look_at from the server

const feed = $("liveFeed");

/* ---------------------------------------------------------------- drawing */

function elapsed(step) {
  if (!step.ended_at || step.state === "info") return "";
  const ms = step.ended_at - step.started_at;
  if (ms < 50) return "";
  return ms < 10000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms / 1000)}s`;
}

const clockOf = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function visible(step) {
  if (filter === "trades") return TRADE_KINDS.has(step.kind);
  if (filter === "problems") return step.state === "failed" || step.kind === "warn";
  return true;
}

function rowHtml(step) {
  const lines = step.lines || [];
  const open = expanded.has(step.id);
  const shown = open ? lines : lines.slice(0, LINES_SHOWN);
  const hidden = lines.length - shown.length;
  const detail = step.detail
    ? `<div class="lv-detail"><span class="lv-hook">⎿</span><span>${esc(step.detail)}</span></div>` : "";
  const list = shown.length ? `
    <ul class="lv-lines">${shown.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    ${hidden > 0 ? `<button class="lv-more" data-more="${step.id}">${esc(t("live.more", { n: hidden }))}</button>` : ""}
    ${open && lines.length > LINES_SHOWN ? `<button class="lv-more" data-less="${step.id}">${esc(t("live.less"))}</button>` : ""}` : "";
  return `
    <div class="lv-row">
      <i class="lv-dot" aria-hidden="true"></i>
      <div class="lv-body">
        <div class="lv-title"><span>${esc(step.title)}</span><time title="${esc(clockOf(step.started_at))}">${esc(elapsed(step))}</time></div>
        ${detail}${list}
      </div>
    </div>`;
}

function stepNode(step) {
  const node = document.createElement("article");
  node.className = `lv-step k-${step.kind} s-${step.state}`;
  node.dataset.id = step.id;
  node.hidden = !visible(step);
  node.innerHTML = rowHtml(step);
  return node;
}

// A look starts with the market check: mark it so a long feed reads in rounds.
function dividerFor(step) {
  const node = document.createElement("div");
  node.className = "lv-divider";
  node.dataset.for = step.id;
  node.hidden = filter !== "all";
  node.innerHTML = `<span>${esc(t("live.look", { time: clockOf(step.started_at).slice(0, 5) }))}</span>`;
  return node;
}

function nearBottom() {
  return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90;
}

function stick(wasNear) {
  if (wasNear) feed.scrollTop = feed.scrollHeight;
}

function renderAll() {
  const wasNear = true;
  feed.innerHTML = "";
  const ordered = [...steps.values()].sort((a, b) => a.id - b.id);
  const frag = document.createDocumentFragment();
  for (const step of ordered) {
    if (step.kind === "clock") frag.appendChild(dividerFor(step));
    frag.appendChild(stepNode(step));
  }
  feed.appendChild(frag);
  $("liveEmpty").hidden = steps.size > 0;
  stick(wasNear);
  renderHeader();
}

function upsert(step) {
  const wasNear = nearBottom();
  const known = steps.has(step.id);
  steps.set(step.id, step);

  const existing = feed.querySelector(`.lv-step[data-id="${step.id}"]`);
  if (known && existing) {
    existing.className = `lv-step k-${step.kind} s-${step.state}`;
    existing.hidden = !visible(step);
    existing.innerHTML = rowHtml(step);
  } else {
    if (step.kind === "clock") feed.appendChild(dividerFor(step));
    feed.appendChild(stepNode(step));
    trim();
  }
  $("liveEmpty").hidden = true;
  stick(wasNear);
  renderHeader();
  publish();
}

function trim() {
  if (steps.size <= CAP) return;
  const ordered = [...steps.keys()].sort((a, b) => a - b);
  for (const id of ordered.slice(0, steps.size - CAP)) {
    steps.delete(id);
    expanded.delete(id);
    feed.querySelector(`.lv-step[data-id="${id}"]`)?.remove();
    feed.querySelector(`.lv-divider[data-for="${id}"]`)?.remove();
  }
}

/* Home's "now" card shows the last few steps too. */
function publish() {
  const latest = [...steps.values()].sort((a, b) => b.id - a.id).slice(0, 3);
  window.mtSteps = latest;
  window.dispatchEvent(new CustomEvent("mt:steps", { detail: latest }));
}

/* ----------------------------------------------------------------- header */

function running() {
  let last = null;
  for (const step of steps.values()) if (step.state === "running" && (!last || step.id > last.id)) last = step;
  return last;
}

function renderHeader() {
  const status = $("liveStatus");
  const dot = $("liveDot");
  const active = running();
  let text;
  let state = "idle";

  if (active) {
    text = look.focus ? t("live.looking", { symbol: look.focus }) : active.title;
    state = "busy";
  } else if (look.running === false) {
    text = t("live.stopped");
    state = "stopped";
  } else if (look.next_look_at) {
    const left = Math.max(0, Math.round((new Date(look.next_look_at) - Date.now()) / 1000));
    text = left > 120 ? t("live.nextMin", { m: Math.ceil(left / 60) }) : t("live.next", { s: left });
  } else {
    text = t("live.working");
  }
  status.textContent = text;
  dot.dataset.state = state;
  // A small pulse on the tab while real work is in flight and you are elsewhere.
  const tabDot = $("liveTabDot");
  if (tabDot) tabDot.hidden = !(active && activeView !== "live");
}

let activeView = "home";

setInterval(renderHeader, 1000);

/* ---------------------------------------------------------------- actions */

$("liveLook").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  button.disabled = true;
  try {
    await fetch(q("/api/engine/scan"), { method: "POST" });
    $("liveStatus").textContent = t("live.asked");
  } catch { /* the header keeps the real state */ }
  setTimeout(() => { button.disabled = false; }, 5000);
});

$("liveFilter").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-filter]");
  if (!chip) return;
  filter = chip.dataset.filter;
  document.querySelectorAll("#liveFilter [data-filter]").forEach((c) => c.classList.toggle("on", c === chip));
  feed.querySelectorAll(".lv-step").forEach((node) => {
    node.hidden = !visible(steps.get(Number(node.dataset.id)) || {});
  });
  feed.querySelectorAll(".lv-divider").forEach((node) => { node.hidden = filter !== "all"; });
  feed.scrollTop = feed.scrollHeight;
});

feed.addEventListener("click", (e) => {
  const more = e.target.closest("[data-more]");
  const less = e.target.closest("[data-less]");
  const id = Number((more || less)?.dataset.more || (more || less)?.dataset.less);
  if (!id || !steps.has(id)) return;
  if (more) expanded.add(id); else expanded.delete(id);
  const node = feed.querySelector(`.lv-step[data-id="${id}"]`);
  if (node) node.innerHTML = rowHtml(steps.get(id));
});

/* ----------------------------------------------------------------- wiring */

async function load() {
  try {
    const res = await fetch(q("/api/steps"));
    if (!res.ok) return;
    const data = await res.json();
    steps.clear();
    for (const step of data.steps || []) steps.set(step.id, step);
    look = { running: data.running, focus: data.focus, next_look_at: data.next_look_at };
    renderAll();
    publish();
  } catch { /* the socket fills it in */ }
}

window.addEventListener("mt:ws", (e) => {
  const msg = e.detail;
  if (msg.type === "step" && msg.step) upsert(msg.step);
});

window.addEventListener("mt:status", (e) => {
  const s = e.detail;
  look = { running: s.running, focus: s.focus, next_look_at: s.next_look_at };
  renderHeader();
});

// Coming back to the tab after the socket dropped: catch up from the server.
window.addEventListener("mt:view", (e) => {
  activeView = e.detail;
  if (e.detail === "live") load();
  renderHeader();
});
window.addEventListener("mt:lang", () => renderAll());

load();
