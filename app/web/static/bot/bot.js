/* Money Bot 12.0 console: entry point (B1.1, B2).
 *
 * Starts the store, draws the top bar's account and market chips, and loads
 * the components. One /api/bot and one /api/bot/log on open, /api/bot again
 * every 5 s while the page is visible, live lines from the socket.
 */

import { $, T } from "./util.js";
import { store, emit, loadSnap, loadLog, loadToday, addLine, mergeBot, fillGap, setTab } from "./store.js";
import "./tiles.js";
import "./crew.js";
import "./log.js";
import "./ledger.js";
import "./side.js";
import "./queue.js";
import "./funnel.js";

/* ------------------------------------------------------------- top bar */

function accountChip(a) {
  const el = $("mbAccount");
  if (!el) return;
  if (!a) { el.dataset.kind = "none"; el.textContent = "—"; return; }
  const kind = a.mode !== "live" ? "paper" : a.armed ? "armed" : "live";
  el.dataset.kind = kind;
  // Arm keeps its old behaviour (chart.js) but only exists on a real account.
  $("btnArm")?.classList.toggle("mb-nolive", a.mode !== "live");
  el.textContent = T(`account.${kind}`);
  const book = a.book ? T(`book.${a.book}`) : "";
  el.title = [T(`account.${kind}Tip`), book].filter(Boolean).join(" · ");
}

function marketChip(m) {
  const el = $("mbMarket");
  if (!el) return;
  el.textContent = m && m.label ? m.label : "…";
  const led = $("marketLed");
  if (led && m) led.className = `dot ${m.open ? "open" : ""}`;
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (!changed.has("snap") && !changed.has("all")) return;
  const s = store.snap;
  accountChip(s && s.account);
  marketChip(s && s.market);
});

/* --------------------------------------------------------------- live */

window.addEventListener("mt:ws", (e) => {
  const msg = e.detail || {};
  if (msg.type === "bot_log") addLine(msg.line);
  else if (msg.type === "bot") mergeBot(msg);
});

window.addEventListener("mt:ws-state", (e) => {
  const down = e.detail === "closed";
  const was = store.ws;
  store.ws = down ? "down" : "open";
  const bar = $("mbWsBar");
  if (bar) bar.hidden = !down;
  if (!down && was === "down") fillGap();
  emit("ws");
});

window.addEventListener("mt:lang", () => { loadSnap(); loadLog(); loadToday(); });
window.addEventListener("mb:logtab", (e) => setTab(e.detail));

setInterval(() => { if (!document.hidden) loadSnap(); }, 5000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadSnap(); });

loadSnap();
loadLog();
loadToday();

// The empty state's buttons and anything else that only needs a known endpoint.
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-mb-go]");
  if (b && window.showView) window.showView(b.dataset.mbGo);
});

