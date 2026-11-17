/* The ledger tab (B2.9): closed trades for today / week / all, the sum row
   and the day's equity line. Every row is a closed trade from /api/bot/ledger. */

import { $, T, esc, money, pct, tone, minutes, hms } from "./util.js";
import { store, loadLedger, setFocus } from "./store.js";

const host = $("mbLedger");

function curve(points) {
  if (!Array.isArray(points) || points.length < 2) return "";
  const xs = points.map((p) => p[0]); const ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (x1 === x0 || y1 === y0) return "";
  const d = points.map((p, i) => `${i ? "L" : "M"}${(((p[0] - x0) / (x1 - x0)) * 300).toFixed(1)},${(40 - ((p[1] - y0) / (y1 - y0)) * 40).toFixed(1)}`).join("");
  const up = ys[ys.length - 1] >= ys[0];
  return `<svg class="mb-curve t-${up ? "good" : "bad"}" viewBox="0 -2 300 44" preserveAspectRatio="none" role="img" aria-label="${esc(T("ledger.curve"))}"><path d="${d}"/></svg>`;
}

function draw() {
  if (!host || store.tab !== "ledger") return;
  const l = store.ledger;
  const ranges = ["today", "week", "all"].map((r) => `<button class="mb-seg${r === store.range ? " on" : ""}" type="button" data-range="${r}" aria-pressed="${r === store.range}">${esc(T(`ledger.${r}`))}</button>`).join("");
  let body;
  if (!l) body = "";
  else if (l.error) body = `<p class="mb-empty">${esc(T("err.load"))} <button class="mb-btn" type="button" data-range="${store.range}">${esc(T("err.retry"))}</button></p>`;
  else if (!l.fills || !l.fills.length) body = `<p class="mb-empty">${esc(T("ledger.empty"))}</p>`;
  else {
    const s = l.sum || {};
    body = `${curve(l.curve)}
    <table class="mb-table"><thead><tr>
      <th>${esc(T("ledger.symbol"))}</th><th>${esc(T("ledger.reason"))}</th><th class="r">${esc(T("ledger.qty"))}</th>
      <th class="r">${esc(T("ledger.entry"))}</th><th class="r">${esc(T("ledger.exit"))}</th><th class="r">${esc(T("ledger.time"))}</th>
      <th class="r">${esc(T("ledger.pnl"))}</th></tr></thead><tbody>
      ${l.fills.map((f) => `<tr data-sym="${esc(f.symbol)}" tabindex="0">
        <td class="mono">${esc(f.symbol)}</td><td>${esc(f.reason)}</td><td class="r num">${esc(f.qty)}</td>
        <td class="r num">${esc(money(f.entry))}</td><td class="r num">${esc(money(f.exit))}</td>
        <td class="r num" title="${esc(hms(f.closed_at))}">${esc(minutes(f.minutes))}</td>
        <td class="r num t-${tone(f.pnl)}">${esc(money(f.pnl, { sign: true }))} <small>${esc(pct(f.pct))}</small></td></tr>`).join("")}
      </tbody><tfoot><tr><td colspan="2">${esc(T("ledger.sum", { n: s.count ?? 0, w: s.wins ?? 0 }))}</td>
        <td class="r" colspan="3">${s.profit_factor == null ? "" : esc(T("ledger.pf", { v: s.profit_factor }))}</td>
        <td class="r num">${esc(minutes(s.avg_minutes))}</td>
        <td class="r num t-${tone(s.pnl)}">${esc(money(s.pnl, { sign: true }))}</td></tr></tfoot></table>`;
  }
  host.innerHTML = `<div class="mb-segs" role="group" aria-label="${esc(T("ledger.range"))}">${ranges}</div>${body}`;
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("ledger") || changed.has("tab") || changed.has("all")) draw();
});

host?.addEventListener("click", (e) => {
  const r = e.target.closest("[data-range]");
  if (r) { loadLedger(r.dataset.range); return; }
  const row = e.target.closest("tr[data-sym]");
  if (row) setFocus(row.dataset.sym);
});
host?.addEventListener("keydown", (e) => {
  const row = e.target.closest("tr[data-sym]");
  if (row && e.key === "Enter") setFocus(row.dataset.sym);
});
