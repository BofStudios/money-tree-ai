/* The console's one store (B2, B3.12).
 *
 * Reads /api/bot and /api/bot/log, merges the live socket's "bot_log" and
 * "bot" events (chart.js owns the socket and re-emits every message as
 * "mt:ws"), and announces "bot:update" at most once per animation frame.
 * Components listen to that and nothing else; none of them fetch on their own.
 */

import { api, lang } from "./util.js";

const MAX_LINES = 200;                     // DOM ceiling for the log (B2.10)
const TAB_VERBS = {
  orders: new Set(["order", "fill", "partial", "exit", "stop", "target"]),
  risk: new Set(["veto", "pause", "resume", "arm", "disarm"]),
};

export const store = {
  snap: null,             // /api/bot
  lines: [],              // log lines for the current tab + agent filter, oldest first
  head: 0,                // highest n seen
  more: true,             // older lines may exist
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
export function emit(...what) {
  what.forEach((w) => store.changed.add(w));
  if (frame) return;
  if (document.hidden) { frame = -1; return; }   // catch up once, on return
  frame = requestAnimationFrame(() => {
    frame = 0;
    const changed = new Set(store.changed);
    store.changed.clear();
    window.dispatchEvent(new CustomEvent("bot:update", { detail: { store, changed } }));
  });
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
    store.more = store.lines.length >= MAX_LINES;
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
  if (store.lines.length > MAX_LINES) { store.lines.splice(0, store.lines.length - MAX_LINES); store.more = true; }
  emit("line");
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
