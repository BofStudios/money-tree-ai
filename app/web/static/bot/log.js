/* agent.log (B2.8–B2.14): the console's heart.
 *
 * #n · HH:MM:SS (NY time on hover) · agent · verb · text · money. Colour from
 * the server's level, never guessed from the words. At most ~200 lines in the
 * DOM. Follows the bottom only while the owner is at the bottom; otherwise a
 * "↓ n new lines" button. Plain selectable text, so lines can be copied.
 */

import { $, T, esc, hms, nyTime, money, tone } from "./util.js";
import { store, setTab, setAgent, setQuery, setFocus } from "./store.js";

const LEVELS = new Set(["info", "good", "bad", "warn", "error"]);
const box = $("mbLines");
let atBottom = true;
let drawnTab = null;
let seenN = 0;          // the last line the owner has seen at the bottom
const fresh = () => store.lines.filter((l) => l.n > seenN).length;

function sym(text, symbol) {
  const safe = esc(text);
  if (!symbol) return safe;
  const s = esc(symbol);
  // Make the line's own symbol clickable; it is the server's field, not a guess.
  const re = new RegExp(`\\b${s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
  return re.test(safe) ? safe.replace(re, `<button class="mb-sym" type="button" data-sym="${s}">${s}</button>`)
    : `<button class="mb-sym" type="button" data-sym="${s}">${s}</button> ${safe}`;
}

function row(l) {
  const level = LEVELS.has(l.level) ? l.level : "info";
  const m = l.money && typeof l.money.pnl === "number"
    ? `<span class="mb-money t-${tone(l.money.pnl)} num">${esc(money(l.money.pnl, { sign: true }))}</span>` : "";
  return `<div class="mb-line lv-${level}" data-n="${l.n}">`
    + `<span class="mb-n num">#${l.n}</span>`
    + `<time class="mb-t num" title="${esc(nyTime(l.at))}">${hms(l.at)}</time>`
    + `<span class="mb-who" data-agent="${esc(l.agent)}">${esc(l.agent)}</span>`
    + `<span class="mb-verb">${esc(l.verb)}</span>`
    + `<span class="mb-text">${sym(l.text, l.symbol)}</span>${m}</div>`;
}

function visible() {
  const q = store.query;
  if (!q) return store.lines;
  return store.lines.filter((l) => `${l.text} ${l.symbol || ""} ${l.agent} ${l.verb}`.toLowerCase().includes(q));
}

function empty() {
  const s = store.snap;
  if (store.query) return `<p class="mb-empty">${esc(T("log.noMatch"))}</p>`;
  if (store.agent || store.tab !== "agent") return `<p class="mb-empty">${esc(T("log.noneHere"))}</p>`;
  const stopped = s && s.account && (s.account.engine !== "running" || s.account.halted);
  const closed = s && s.market && !s.market.open;
  return `<div class="mb-empty"><b>${esc(T("log.empty"))}</b>
    <p>${esc(stopped ? T("log.emptyStopped") : closed ? T("log.emptyClosed") : T("log.emptyHint"))}</p>
    ${stopped ? `<p class="mb-dim">${esc(T("log.emptyStart"))}</p>` : ""}</div>`;
}

function draw(full) {
  if (!box) return;
  const rows = visible();
  const keep = atBottom;
  const before = box.scrollHeight - box.scrollTop;
  box.innerHTML = rows.length ? rows.map(row).join("") : empty();
  if (keep) { box.scrollTop = box.scrollHeight; seenN = store.head; }
  else if (!full) box.scrollTop = box.scrollHeight - before;
  newButton();
}

function newButton() {
  const b = $("mbNewLines");
  if (!b) return;
  const n = fresh();
  b.hidden = atBottom || n <= 0;
  b.textContent = T("log.newLines", { n });
}

function filterChip() {
  const el = $("mbLogFilter");
  if (!el) return;
  const c = store.agent && store.snap && (store.snap.crew || []).find((x) => x.id === store.agent);
  el.hidden = !store.agent;
  el.innerHTML = store.agent
    ? `<span data-agent="${esc(store.agent)}">${esc(c ? c.name : store.agent)}</span><button class="mb-x" type="button" data-clear-agent aria-label="${esc(T("log.clearFilter"))}">×</button>` : "";
}

function tabs() {
  document.querySelectorAll("#mbLogTabs .mb-tab").forEach((b) => {
    const on = b.dataset.logtab === store.tab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", String(on));
  });
  const ledger = store.tab === "ledger";
  if (box) box.hidden = ledger;
  const lg = $("mbLedger");
  if (lg) lg.hidden = !ledger;
  const search = $("mbLogSearch");
  if (search) search.hidden = ledger;
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("tab") || changed.has("agent") || changed.has("all") || drawnTab !== store.tab) { tabs(); filterChip(); drawnTab = store.tab; }
  if (store.tab === "ledger") return;
  if (changed.has("log")) { atBottom = true; }
  if (changed.has("log") || changed.has("line") || changed.has("query") || changed.has("all")) draw(changed.has("log"));
  else if (changed.has("snap") && !store.lines.length) draw(true);   // empty-state words follow the engine
});

box?.addEventListener("scroll", () => {
  atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
  if (atBottom) { seenN = store.head; newButton(); }
}, { passive: true });

$("mbNewLines")?.addEventListener("click", () => {
  atBottom = true; seenN = store.head;
  box.scrollTop = box.scrollHeight;
  newButton();
});

$("mbLogTabs")?.addEventListener("click", (e) => {
  const b = e.target.closest("[data-logtab]");
  if (b) setTab(b.dataset.logtab);
});
$("mbLogTabs")?.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
  const all = [...document.querySelectorAll("#mbLogTabs .mb-tab")];
  const i = all.indexOf(document.activeElement);
  if (i < 0) return;
  const next = all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
  next.focus(); setTab(next.dataset.logtab);
});

$("mbLogFilter")?.addEventListener("click", (e) => {
  if (e.target.closest("[data-clear-agent]") && store.agent) setAgent(store.agent);
});

let typing = 0;
$("mbLogSearch")?.addEventListener("input", (e) => {
  clearTimeout(typing);
  typing = setTimeout(() => setQuery(e.target.value), 120);
});

box?.addEventListener("click", (e) => {
  const s = e.target.closest("[data-sym]");
  if (s) setFocus(s.dataset.sym);
});
