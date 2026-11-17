/* Strategy queue (B2.19): ideas waiting in line, as chips. Ones waiting for
   the owner's approval get Approve / Skip (the existing proposal endpoints).
   The countdown comes from the server's expires_at. */

import { $, T, esc, api } from "./util.js";
import { store, loadSnap, setFocus } from "./store.js";

const host = $("mbQueue");
const STATES = new Set(["waiting", "approval", "blocked"]);
let note = "";

function left(ms) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((ms - Date.now()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function chip(q) {
  const state = STATES.has(q.state) ? q.state : "waiting";
  return `<div class="mb-q st-${state}" data-agent="${esc(q.by || "")}" title="${esc(q.why || "")}">
    <button class="mb-sym" type="button" data-sym="${esc(q.symbol)}">${esc(q.symbol)}</button>
    <span>${esc(q.kind || "")}</span><span class="num">${esc(q.votes || "")}</span>
    <span class="mb-q-state">${esc(T(`queue.${state}`))}</span>
    ${q.expires_at ? `<time class="num mb-dim" data-exp="${q.expires_at}">${left(q.expires_at)}</time>` : ""}
    ${state === "approval" ? `<button class="mb-btn mb-ok" type="button" data-approve="${esc(q.id)}">${esc(T("queue.approve"))}</button>
      <button class="mb-btn" type="button" data-skip="${esc(q.id)}">${esc(T("queue.skip"))}</button>` : ""}
  </div>`;
}

function draw() {
  if (!host) return;
  const q = (store.snap && store.snap.queue) || [];
  host.innerHTML = `<span class="mb-box-label">${esc(T("queue.title"))}</span>
    <div class="mb-q-row">${q.length ? q.map(chip).join("") : `<span class="mb-dim">${esc(T("queue.empty"))}</span>`}</div>
    ${note ? `<p class="mb-note">${esc(note)}</p>` : ""}`;
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("all")) draw();
});
setInterval(() => {
  if (document.hidden || !host) return;
  host.querySelectorAll("[data-exp]").forEach((t) => { t.textContent = left(Number(t.dataset.exp)); });
}, 1000);

host?.addEventListener("click", async (e) => {
  const s = e.target.closest("[data-sym]");
  if (s) { setFocus(s.dataset.sym); return; }
  const a = e.target.closest("[data-approve]"), k = e.target.closest("[data-skip]");
  if (!a && !k) return;
  const id = (a || k).dataset.approve || (a || k).dataset.skip;
  (a || k).disabled = true;
  try { await api("POST", `/api/proposals/${encodeURIComponent(id)}/${a ? "approve" : "skip"}`); note = ""; }
  catch (err) { note = T("queue.failed", { why: err.message }); }
  loadSnap();
});
