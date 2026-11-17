/* The crew: seven cards (B2.4–B2.7). State in colour and in a word. The 2 px
   edge shows only while the server says "work"; nothing blinks on its own.
   Click or Enter filters agent.log; "i" opens how the agent works (/api/desk). */

import { $, T, esc, ago, glyph, api, lang } from "./util.js";
import { store, setAgent } from "./store.js";

const STATES = new Set(["idle", "work", "wait", "veto", "off", "error"]);
let desk = null;
let openInfo = null;

function card(c) {
  const state = STATES.has(c.state) ? c.state : "idle";
  const on = store.agent === c.id;
  const last = c.last || T("crew.nothing");
  return `<button class="mb-card st-${state}" type="button" data-agent="${esc(c.id)}" aria-pressed="${on}"
      aria-label="${esc(`${c.name}, ${c.role_label || c.role}: ${T(`state.${state}`)}. ${last}`)}">
    <span class="mb-card-head">${glyph(c.id)}<b>${esc(c.name)}</b><small>${esc(c.role_label || c.role)}</small></span>
    <span class="mb-card-state"><i aria-hidden="true"></i>${esc(T(`state.${state}`))}<em>${esc(ago(c.last_at))}</em></span>
    <span class="mb-card-last" title="${esc(last)}">${esc(last)}</span>
  </button>`;
}

function draw() {
  const host = $("mbCrew");
  if (!host) return;
  const crew = (store.snap && store.snap.crew) || [];
  host.innerHTML = crew.map(card).join("") + (openInfo ? infoPanel() : "");
}

function infoPanel() {
  const c = ((store.snap && store.snap.crew) || []).find((x) => x.id === openInfo);
  if (!c) return "";
  // /api/desk: {agents: [{id, name, role, how, stat, items: [text]}]}
  const entry = desk && Array.isArray(desk.agents) ? desk.agents.find((d) => d.id === c.id) : null;
  const body = entry
    ? `<p>${esc(entry.how)}</p>${entry.stat ? `<p class="mb-dim">${esc(entry.stat)}</p>` : ""}${Array.isArray(entry.items)
      ? `<ul>${entry.items.slice(0, 6).map((p) => `<li>${esc(typeof p === "string" ? p : p.text || p.title || "")}</li>`).join("")}</ul>` : ""}`
    : `<p class="mb-dim">${esc(T("crew.noDesk"))}</p>`;
  return `<div class="mb-crew-info" data-agent="${esc(c.id)}" role="region" aria-label="${esc(c.name)}">
    <header>${glyph(c.id)}<b>${esc(c.name)}</b><small>${esc(c.role_label || c.role)}</small>
      <button class="mb-x" type="button" data-info-close aria-label="${esc(T("close"))}">×</button></header>
    ${body}
    <p class="mb-dim">${esc(T("crew.today", { n: c.today?.lines ?? 0 }))}</p>
  </div>`;
}

async function info(id) {
  openInfo = openInfo === id ? null : id;
  if (openInfo && !desk) {
    try { desk = await api("GET", `/api/desk?lang=${lang() === "tr" ? "tr" : "en"}`); } catch { desk = {}; }
  }
  draw();
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("agent") || changed.has("all")) draw();
});
// The "x min ago" words age without new data.
setInterval(() => { if (!document.hidden && store.snap) draw(); }, 30000);

const host = $("mbCrew");
let pressTimer = 0;
host?.addEventListener("click", (e) => {
  if (e.target.closest("[data-info-close]")) { openInfo = null; draw(); return; }
  const b = e.target.closest(".mb-card");
  if (b && !b.dataset.longPressed) setAgent(b.dataset.agent);
  if (b) delete b.dataset.longPressed;
});
host?.addEventListener("keydown", (e) => {
  const b = e.target.closest(".mb-card");
  if (b && (e.key === "i" || e.key === "I")) { e.preventDefault(); info(b.dataset.agent); }
});
host?.addEventListener("pointerdown", (e) => {
  const b = e.target.closest(".mb-card");
  if (!b) return;
  pressTimer = setTimeout(() => { b.dataset.longPressed = "1"; info(b.dataset.agent); }, 550);
});
["pointerup", "pointerleave", "pointercancel"].forEach((ev) => host?.addEventListener(ev, () => clearTimeout(pressTimer)));
