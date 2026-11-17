/* The console's one store (B2, B3.12).
 *
 * Reads /api/bot and /api/bot/log, merges the live socket's "bot_log" and
 * "bot" events (chart.js owns the socket and re-emits every message as
 * "mt:ws"), and announces "bot:update" at most once per animation frame.
 * Components listen to that and nothing else; none of them fetch on their own.
 */

import { api, lang } from "./util.js";

const MAX_LINES = 200;                     // DOM ceiling for the log (B2.10)
const MAX_PAGED = 600;                     // ceiling while the owner reads older pages
const PAGE = 100;
const TAB_VERBS = {
  orders: new Set(["order", "fill", "partial", "exit", "stop", "target"]),
  risk: new Set(["veto", "pause", "resume", "arm", "disarm"]),
};

export const store = {
  snap: null,             // /api/bot
  lines: [],              // log lines for the current tab + agent filter, oldest first
  head: 0,                // highest n seen
  more: true,             // older lines may exist
  paged: false,           // older pages were loaded above the live tail
  loadingOlder: false,
  ledger: null,           // /api/bot/ledger for store.range (ledger tab)
  today: null,            // /api/bot/ledger?range=today (side panel: closed today)
  range: "today",
  tab: "agent",           // agent | orders | risk | ledger
  agent: null,            // crew filter
  query: "",              // client-side search
  focus: null,            // a symbol the owner clicked; null = the server's focus
  ws: "open",
  error: null,
  loaded: false,
  changed: new Set(),     // what moved since the last draw
};

let frame = 0;
let backup = 0;
export function emit(...what) {
  what.forEach((w) => store.changed.add(w));
  if (frame > 0) return;                         // a draw is already scheduled
  // Hidden: wait. -1 is not a lock; the next emit while visible (or the
  // visibilitychange below) schedules the catch-up draw.
  if (document.hidden) { frame = -1; return; }
  // One draw per frame. A timer backs the frame up: a covered or occluded
  // window can stop animation frames while still reporting "visible".
  const flush = () => {
    if (frame <= 0) return;
    cancelAnimationFrame(frame); clearTimeout(backup);
    frame = 0;
    const changed = new Set(store.changed);
    store.changed.clear();
    window.dispatchEvent(new CustomEvent("bot:update", { detail: { store, changed } }));
  };
  frame = requestAnimationFrame(flush);
  backup = setTimeout(flush, 120);
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && frame === -1) { frame = 0; emit("all"); }
});

const langQ = () => `lang=${lang() === "tr" ? "tr" : "en"}`;

function matches(line) {
  if (store.agent && line.agent !== store.agent) return false;
  const verbs = TAB_VERBS[store.tab];
  return !verbs || verbs.has(line.verb);
}

function logQuery(extra = "") {
  const p = [`limit=${MAX_LINES}`, langQ()];
  if (store.agent) p.push(`agent=${encodeURIComponent(store.agent)}`);
  if (TAB_VERBS[store.tab]) p.push(`tab=${store.tab}`);
  return `/api/bot/log?${p.join("&")}${extra}`;
}

export async function loadSnap() {
  try {
    store.snap = await api("GET", `/api/bot?${langQ()}`);
    store.error = null;
  } catch (err) {
    store.error = err.message || "error";
  }
  store.loaded = true;
  emit("snap");
}

export async function loadLog() {
  try {
    const res = await api("GET", logQuery());
    store.lines = res.lines || [];
    store.head = Math.max(store.head, res.head || 0, ...store.lines.map((l) => l.n));
    store.more = store.lines.length >= MAX_LINES || (store.lines[0] && store.lines[0].n > 1);
    store.paged = false;
  } catch (err) {
    store.error = err.message || "error";
  }
  emit("log");
}

/** After a dropped socket: fetch everything after the last line we have. */
export async function fillGap() {
  const after = store.lines.length ? store.lines[store.lines.length - 1].n : 0;
  try {
    const res = await api("GET", logQuery(`&after=${after}`));
    (res.lines || []).forEach(addLine);
  } catch { /* the next reconnect tries again */ }
  loadSnap();
}

export function addLine(line) {
  if (!line || typeof line.n !== "number") return;
  store.head = Math.max(store.head, line.n);
  if (!matches(line)) { emit("head"); return; }
  const last = store.lines[store.lines.length - 1];
  if (last && line.n <= last.n) {                    // never a double line
    if (store.lines.some((l) => l.n === line.n)) return;
    store.lines.push(line);
    store.lines.sort((a, b) => a.n - b.n);
  } else {
    store.lines.push(line);
  }
  if (["exit", "stop", "target"].includes(line.verb)) { loadToday(); if (store.tab === "ledger") loadLedger(); }
  const cap = store.paged ? MAX_PAGED : MAX_LINES;
  if (store.lines.length > cap) { store.lines.splice(0, store.lines.length - cap); store.more = true; }
  emit("line");
}

/** Scrolled to the top: the page just before the oldest loaded line. */
export async function loadOlder() {
  const first = store.lines[0];
  if (!first || !store.more || store.loadingOlder || store.lines.length >= MAX_PAGED) return;
  store.loadingOlder = true;
  try {
    const res = await api("GET", logQuery(`&before=${first.n}`).replace(`limit=${MAX_LINES}`, `limit=${PAGE}`));
    const older = (res.lines || []).filter((l) => l.n < first.n);
    store.lines = older.concat(store.lines);
    store.more = older.length >= PAGE && older[0].n > 1;
    store.paged = true;
  } catch { /* scrolling up again retries */ }
  store.loadingOlder = false;
  emit("older");
}

export async function loadLedger(range = store.range) {
  store.range = range;
  try { store.ledger = await api("GET", `/api/bot/ledger?range=${range}&${langQ()}`); }
  catch (err) { store.ledger = { error: err.message || "error" }; }
  emit("ledger");
}

export async function loadToday() {
  try { store.today = await api("GET", `/api/bot/ledger?range=today&${langQ()}`); }
  catch (err) { store.today = { error: err.message || "error" }; }
  emit("today");
}

/* ------------------------------------------------------------- actions */

export function setTab(tab) {
  if (tab === store.tab) return;
  store.tab = tab;
  emit("tab");
  if (tab === "ledger") loadLedger(); else loadLog();
}

export function setAgent(id) {
  store.agent = store.agent === id ? null : id;
  emit("agent");
  if (store.tab === "ledger") store.tab = "agent";
  loadLog();
}

export function setQuery(q) { store.query = q.trim().toLowerCase(); emit("query"); }

export function setFocus(symbol) { store.focus = symbol || null; emit("focus"); }

export function mergeBot(ev) {
  if (!store.snap) return;
  for (const k of ["tiles", "crew", "queue", "focus", "risk", "funnel", "account", "market", "proof"]) {
    if (ev[k] !== undefined) store.snap[k] = ev[k];
  }
  emit("snap");
}
