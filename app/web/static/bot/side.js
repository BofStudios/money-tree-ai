/* Right panel (B2.15–B2.18): the focus symbol, its 1-minute chart with entry,
   stop and target lines, and the trades closed today. "Close" needs a second
   click (the privacy.js pattern), never confirm(). */

import { $, T, esc, money, pct, tone, minutes, api } from "./util.js";
import { store, setFocus, loadSnap } from "./store.js";

const host = $("mbSide");
let chart = null, series = null, lines = [], chartSym = null;
let armClose = null, armTimer = 0, closeNote = "";

function css(name) { return getComputedStyle(host).getPropertyValue(name).trim(); }

function head(f, sym) {
  // An open position is the one focus with a quantity and an open time (why is translated text).
  if (f && f.symbol === sym && f.qty != null && f.opened_at) {
    const open = f.opened_at ? minutes(Math.max(0, Math.round((Date.now() - f.opened_at) / 60000))) : "";
    return `<div class="mb-side-head"><b class="mono">${esc(sym)}</b>
      <span class="num t-${tone(f.pnl)}">${esc(money(f.pnl, { sign: true }))} (${esc(pct(f.pnl_pct))})</span>
      <span class="mb-dim">${esc(T("side.open", { t: open }))}</span>
      <button class="mb-btn mb-close${armClose === sym ? " armed" : ""}" type="button" data-close="${esc(sym)}">${esc(armClose === sym ? T("side.closeSure") : T("side.close"))}</button></div>
      ${closeNote ? `<p class="mb-note">${esc(closeNote)}</p>` : ""}`;
  }
  const word = f && f.symbol === sym && f.why ? f.why : store.focus ? T("side.picked") : "";
  return `<div class="mb-side-head"><b class="mono">${esc(sym)}</b><span class="mb-dim">${esc(word)}</span>
    ${store.focus ? `<button class="mb-x" type="button" data-unfocus aria-label="${esc(T("side.back"))}">×</button>` : ""}</div>`;
}

async function loadChart(sym, f) {
  const el = $("mbChart");
  if (!el || !window.LightweightCharts) return;
  if (!chart) {
    chart = window.LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: css("--text-3"), fontFamily: css("--mono"), fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: css("--line") } },
      rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false, timeVisible: true },
      crosshair: { mode: 0 },
    });
    series = chart.addCandlestickSeries({
      upColor: css("--good"), downColor: css("--bad"), borderVisible: false,
      wickUpColor: css("--good"), wickDownColor: css("--bad"),
    });
  }
  chartSym = sym;
  let candles = [];
  try { candles = (await api("GET", `/api/candles/${encodeURIComponent(sym)}`)).candles || []; } catch { candles = []; }
  if (chartSym !== sym) return;
  const note = $("mbChartNote");
  if (note) note.hidden = candles.length > 0;
  series.setData(candles);
  lines.forEach((l) => series.removePriceLine(l)); lines = [];
  if (f && f.symbol === sym) {
    const add = (price, color, style, title) => { if (price != null) lines.push(series.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title })); };
    add(f.entry, css("--text-2"), 0, T("side.entry"));
    add(f.stop, css("--bad"), 2, T("side.stop"));
    add(f.target, css("--good"), 2, T("side.target"));
  }
  chart.timeScale().fitContent();
}

function closed() {
  const d = store.today;
  if (!d) return "";
  if (d.error) return `<p class="mb-empty">${esc(T("err.load"))}</p>`;
  const fills = (d.fills || []).slice(-8).reverse();
  const s = d.sum || {};
  return `<div class="mb-closed"><div class="mb-closed-head"><span>${esc(T("side.closedToday"))}</span>
      <span class="num">${s.count ?? 0} · <b class="t-${tone(s.pnl)}">${esc(money(s.pnl ?? 0, { sign: true }))}</b></span></div>
    ${fills.length ? fills.map((f) => `<button class="mb-closed-row" type="button" data-sym="${esc(f.symbol)}">
      <b class="mono">${esc(f.symbol)}</b><span>${esc(f.reason)}</span>
      <span class="num t-${tone(f.pnl)}">${esc(money(f.pnl, { sign: true }))}</span><span class="num mb-dim">${esc(minutes(f.minutes))}</span></button>`).join("")
      : `<p class="mb-dim">${esc(T("side.noneClosed"))}</p>`}</div>`;
}

function draw() {
  if (!host) return;
  const f = store.snap && store.snap.focus;
  const lastClosed = store.today && (store.today.fills || []).slice(-1)[0];
  const sym = store.focus || (f && f.symbol) || (lastClosed && lastClosed.symbol) || null;
  const chartEl = $("mbChart");
  if (!sym) {
    if (chart) { chart.remove(); chart = null; series = null; lines = []; chartSym = null; }
    host.innerHTML = `<div class="mb-side-empty"><b>${esc(T("side.nothing"))}</b><p>${esc(T("side.nothingHint"))}</p></div>${closed()}`;
    return;
  }
  // Keep the chart element alive across redraws; rebuild only the words.
  if (!chartEl) {
    host.innerHTML = `<div id="mbSideHead"></div><div class="mb-chart" id="mbChart"><p class="mb-dim mb-chart-note" id="mbChartNote" hidden>${esc(T("side.noCandles"))}</p></div><div id="mbClosed"></div>`;
    chart = null;
  }
  $("mbSideHead").innerHTML = head(f, sym);
  $("mbClosed").innerHTML = closed();
  if (sym !== chartSym || !chart) loadChart(sym, f);
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("focus") || changed.has("today") || changed.has("all")) draw();
});

host?.addEventListener("click", async (e) => {
  if (e.target.closest("[data-unfocus]")) { setFocus(null); return; }
  const row = e.target.closest("[data-sym]");
  if (row) { setFocus(row.dataset.sym); return; }
  const c = e.target.closest("[data-close]");
  if (!c) return;
  const sym = c.dataset.close;
  if (armClose !== sym) {
    armClose = sym; closeNote = "";
    clearTimeout(armTimer);
    armTimer = setTimeout(() => { armClose = null; draw(); }, 4000);
    draw();
    return;
  }
  armClose = null; clearTimeout(armTimer);
  try { await api("POST", `/api/close/${encodeURIComponent(sym)}`); closeNote = T("side.closeSent"); }
  catch (err) { closeNote = T("side.closeFailed", { why: err.message }); }
  draw(); loadSnap();
});
