/* Four number tiles (B2.1–B2.3). Static, aria-labelled; a 400 ms colour trace
   when a number moves, none under reduced motion. No counting animation. */

import { $, T, esc, money, pct, int, tone, reducedMotion } from "./util.js";
import { store } from "./store.js";

const RANGES = ["today", "week", "all"];
let range = "today";
const prev = {};

function tile(id, label, big, sub, { cls = "", bar = null, button = false, aria = "" } = {}) {
  const tag = button ? "button" : "div";
  return `<${tag} class="mb-tile ${cls}" data-tile="${id}" ${button ? 'type="button"' : ""} aria-label="${esc(aria || `${label}: ${big}`)}">
    <span class="mb-tile-label">${esc(label)}</span>
    <span class="mb-tile-num num">${esc(big)}</span>
    <span class="mb-tile-sub">${sub ? esc(sub) : "&nbsp;"}</span>
    ${bar === null ? "" : `<i class="mb-tile-bar" aria-hidden="true"><b style="width:${Math.min(100, Math.max(0, bar))}%"></b></i>`}
  </${tag}>`;
}

function draw() {
  const host = $("mbTiles");
  if (!host) return;
  const s = store.snap;
  if (!s) {
    host.innerHTML = store.error
      ? `<div class="mb-tile mb-err">${esc(T("err.load"))} <button class="mb-btn" data-mb-retry>${esc(T("err.retry"))}</button></div>`
      : "";
    host.setAttribute("aria-busy", String(!store.error));
    return;
  }
  host.removeAttribute("aria-busy");
  // Real money is the only way: before the real account is connected the numbers
  // would be the background practice engine's, so they are not shown.
  if (!(s.account && s.account.mode === "live")) {
    host.innerHTML = ["fills", "positions", "net.today", "equity"].map((k) => tile(k, T(`tiles.${k}`), "—", T("tiles.notConnected"))).join("");
    return;
  }
  const { fills = {}, positions = {}, net = {}, capital = {} } = s.tiles || {};

  const fillBig = fills.max ? `${int(fills.closed)} / ${int(fills.max)}` : int(fills.closed);
  const fillsHtml = tile("fills", T("tiles.fills"), fillBig, T("tiles.opened", { n: int(fills.opened ?? 0) }),
    { bar: fills.max ? (100 * (fills.closed || 0)) / fills.max : null });

  const posBig = positions.max ? `${int(positions.open)} / ${int(positions.max)}` : int(positions.open);
  const posHtml = tile("positions", T("tiles.positions"), posBig, "");

  const value = range === "today" ? net.today : net[range];
  let netSub = "";
  if (range === "today") netSub = T("tiles.unrealized", { v: money(net.unrealized, { sign: true }) });
  else if (range === "all" && net.since) netSub = T("tiles.since", { d: new Date(net.since).toLocaleDateString() });
  const netBig = money(value, { sign: true });
  const netHtml = tile("net", T(`tiles.net.${range}`), netBig, netSub, {
    cls: `mb-net t-${tone(value)}`, button: true,
    aria: `${T(`tiles.net.${range}`)}: ${netBig}${range === "today" && net.today_pct ? ` (${pct(net.today_pct)})` : ""}. ${T("tiles.netCycle")}`,
  });

  const eqSub = [capital.start_today != null ? T("tiles.start", { v: money(capital.start_today) }) : "",
    capital.budget != null ? T("tiles.budget", { v: money(capital.budget) }) : ""].filter(Boolean).join(" · ");
  const eqHtml = tile("equity", T("tiles.equity"), money(capital.equity), eqSub);

  host.innerHTML = fillsHtml + posHtml + netHtml + eqHtml;

  // A short colour trace on whichever number moved.
  const now = { fills: fills.closed, positions: positions.open, net: value, equity: capital.equity };
  if (!reducedMotion()) {
    for (const [k, v] of Object.entries(now)) {
      if (prev[k] !== undefined && v !== prev[k] && typeof v === "number" && typeof prev[k] === "number") {
        const el = host.querySelector(`[data-tile="${k}"]`);
        if (el) el.classList.add(v > prev[k] ? "flash-up" : "flash-down");
      }
    }
  }
  Object.assign(prev, now);
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("all") || changed.has("range")) draw();
});

$("mbTiles")?.addEventListener("click", (e) => {
  if (e.target.closest("[data-mb-retry]")) { import("./store.js").then((m) => m.loadSnap()); return; }
  if (!e.target.closest('[data-tile="net"]')) return;
  range = RANGES[(RANGES.indexOf(range) + 1) % RANGES.length];
  prev.net = undefined;
  draw();
  $("mbTiles").querySelector('[data-tile="net"]')?.focus();
});
