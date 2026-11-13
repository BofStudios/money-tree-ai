/* The Lab (desktop 10.0).
 *
 *   Replay     Ultra's rules (8.0 and 9.0) on the last days of real
 *              one-minute bars: Freqtrade-style backtest, Jesse-style
 *              metrics, a $ account through it, exits and symbols.
 *   Edge       symbols the replay lost on are skipped by Ultra (switchable).
 *   Analytics  the real, finished trades: profit factor, expectancy,
 *              drawdown, Sharpe/Sortino, by book, hour, weekday, symbol, days.
 *
 * Everything shown is measured. A bad result is shown as bad.
 */

import { getLanguage, t } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("token");
  try { return fromUrl || localStorage.getItem("mt_token") || ""; } catch { return fromUrl || ""; }
})();
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch(q(path), {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

const T = (k, vars) => t("lab." + k, vars);
const tr = () => getLanguage() === "tr";

const n2 = (v, d = 2) => (v == null ? "–" : Number(v).toFixed(d));
const pct = (v, d = 2) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}%`);
const usd = (v) => (v == null ? "–" : `${v < 0 ? "−" : v > 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}`);
const tone = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
const when = (iso) => { try { return new Date(iso).toLocaleString(tr() ? "tr-TR" : undefined, { dateStyle: "short", timeStyle: "short" }); } catch { return iso; } };

let view = "home";
let lab = null;
let stats = null;
let poll = null;

/* ------------------------------------------------------------------ chart */

function curveSvg(curves) {
  const series = [["8.0", curves["8.0"] || [], "lab-c80"], ["9.0", curves["9.0"] || [], "lab-c90"]]
    .filter(([, c]) => c.length > 1);
  if (!series.length) return "";
  const all = series.flatMap(([, c]) => c.map((p) => p.value));
  const lo = Math.min(...all), hi = Math.max(...all);
  const span = hi - lo || 1;
  const W = 640, H = 180, P = 8;
  const lines = series.map(([name, c, cls]) => {
    const pts = c.map((p, i) => `${(P + (i / (c.length - 1)) * (W - 2 * P)).toFixed(1)},${(H - P - ((p.value - lo) / span) * (H - 2 * P)).toFixed(1)}`).join(" ");
    return `<polyline class="${cls}" points="${pts}" />`;
  }).join("");
  const start = series[0][1][0].value;
  const y0 = (H - P - ((start - lo) / span) * (H - 2 * P)).toFixed(1);
  return `
    <div class="lab-chart">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(T("curve"))}">
        <line class="lab-base" x1="0" x2="${W}" y1="${y0}" y2="${y0}" />${lines}
      </svg>
      <div class="lab-legend"><span class="lab-k80">${esc(T("r80"))}</span><span class="lab-k90">${esc(T("r90"))}</span>
        <span class="faint">$${n2(lo)} – $${n2(hi)}</span></div>
    </div>`;
}

function bars(rows, label) {
  if (!rows || !rows.length) return "";
  const max = Math.max(...rows.map((r) => Math.abs(r.net ?? r.sum ?? 0)), 0.0001);
  return `<ul class="lab-bars">${rows.map((r) => {
    const v = r.net ?? r.sum ?? 0;
    return `<li><span>${esc(label(r.key))}</span>
      <i><em class="${v >= 0 ? "up" : "down"}" style="width:${Math.max(2, (Math.abs(v) / max) * 100).toFixed(0)}%"></em></i>
      <b class="${tone(v)}">${r.net != null ? usd(v) : pct(v)}</b><small>${r.trades} · ${n2(r.win_rate, 0)}%</small></li>`;
  }).join("")}</ul>`;
}

/* ----------------------------------------------------------------- render */

function replayHtml() {
  if (!lab) return "";
  const r = lab.report;
  const runBtn = `<button class="primary" id="labRun" ${lab.running ? "disabled" : ""}>${esc(T(lab.running ? "running" : "run"))}</button>`;
  const err = lab.error ? `<p class="note warn">${esc(T("error", { e: lab.error }))}</p>` : "";
  if (!r) {
    return `<section class="mode-block lab-card"><h2>${esc(T("replay"))}</h2><p class="note faint">${esc(T("never"))}</p>${err}<div class="mode-actions">${runBtn}</div></section>`;
  }
  const a = r.rules["8.0"], b = r.rules["9.0"];
  const v = T(`v_${b.verdict}`, { a: n2(b.avg, 3), pf: n2(b.profit_factor), n: b.trades });
  const row = (name, m) => `
    <tr><th>${esc(name)}</th><td>${m.trades}</td><td>${n2(m.win_rate, 1)}%</td>
      <td class="${tone(m.avg)}">${pct(m.avg, 3)}</td><td>${n2(m.profit_factor)}</td>
      <td class="${tone(m.portfolio.profit)}">$${n2(m.portfolio.end)} <small>${pct(m.portfolio.return_pct)}</small></td>
      <td class="down">${pct(m.portfolio.max_drawdown)}</td><td>${n2(m.portfolio.sharpe)}</td><td>${n2(m.portfolio.sortino)}</td></tr>`;
  const exitName = (k) => T(`ex_${k}`);
  const syms = r.symbols.map((s) => `
    <tr class="${r.blocked.includes(s.key) ? "lab-blocked" : ""}"><th>${esc(s.key)}${r.blocked.includes(s.key) ? ` <em>${esc(T("skipped"))}</em>` : ""}</th>
      <td>${s.trades}</td><td>${n2(s.win_rate, 0)}%</td><td class="${tone(s.avg)}">${pct(s.avg, 3)}</td><td class="${tone(s.sum)}">${pct(s.sum)}</td></tr>`).join("");
  const recent = (r.recent || []).slice(0, 14).map((t) => `
    <li><b>${esc(t.symbol)}</b><span>${esc(when(t.at))}</span><em>${esc(exitName(t.why))}</em><i class="${tone(t.pnl)}">${pct(t.pnl, 2)}</i></li>`).join("");
  const edge = lab.edge_rule;
  return `
    <section class="mode-block lab-card lab-${esc(b.verdict)}">
      <h2>${esc(T("replay"))}</h2>
      <p class="lab-verdict">${esc(v)}</p>
      <p class="note faint">${esc(T("replayNote", { d: r.days.length, s: r.symbols_n, b: r.bars.toLocaleString(), c: r.cost_pct }))}</p>
      <div class="mode-actions">${runBtn}<span class="faint">${esc(T("last", { t: when(r.ran_at) }))}${lab.next_run ? ` · ${esc(T("next", { t: when(lab.next_run) }))}` : ""}</span></div>
      ${err}
      <div class="lab-table"><table>
        <thead><tr><th>${esc(T("rule"))}</th><th>${esc(T("trades"))}</th><th>${esc(T("win"))}</th><th>${esc(T("avg"))}</th><th>${esc(T("pf"))}</th>
          <th>${esc(T("account", { s: n2(r.start_cash) }))}</th><th>${esc(T("dd"))}</th><th>${esc(T("sharpe"))}</th><th>${esc(T("sortino"))}</th></tr></thead>
        <tbody>${row(T("r80"), a)}${row(T("r90"), b)}</tbody></table></div>
    </section>
    <section class="mode-block lab-card">
      <h2>${esc(T("curve"))}</h2>
      ${curveSvg(r.curves || {})}
      <p class="note faint">${esc(T("curveNote"))}</p>
    </section>
    <section class="mode-block lab-card">
      <h2>${esc(T("edge"))}</h2>
      <label class="gate"><input type="checkbox" id="labEdge" ${lab.edge ? "checked" : ""}>
        <span class="switch"></span><span><b>${esc(T("edge"))}</b><small>${esc(T("edgeHint", { n: edge.min_trades, a: edge.max_avg }))}</small></span></label>
      <p class="note">${r.blocked.length ? `${esc(T("edgeList"))} <b>${r.blocked.map(esc).join(", ")}</b>` : esc(T("edgeNone"))}</p>
    </section>
    <div class="lab-two">
      <section class="mode-block lab-card"><h2>${esc(T("exits"))}</h2>${bars(r.exits, exitName)}</section>
      <section class="mode-block lab-card"><h2>${esc(T("recent"))}</h2><ul class="lab-recent">${recent}</ul></section>
    </div>
    <section class="mode-block lab-card">
      <h2>${esc(T("symbols"))}</h2>
      <div class="lab-table"><table>
        <thead><tr><th>${esc(T("sym"))}</th><th>${esc(T("trades"))}</th><th>${esc(T("win"))}</th><th>${esc(T("avg"))}</th><th>${esc(T("sum"))}</th></tr></thead>
        <tbody>${syms}</tbody></table></div>
    </section>`;
}

function realHtml() {
  if (!stats) return "";
  const m = stats.money;
  if (!m.trades) {
    return `<section class="mode-block lab-card"><h2>${esc(T("real"))}</h2><p class="note faint">${esc(T("noTrades"))}</p></section>`;
  }
  const k = stats.risk, s = stats.streaks;
  const tile = (label, value, cls = "") => `<div class="lab-tile"><small>${esc(label)}</small><b class="${cls}">${value}</b></div>`;
  const days = (stats.days || []).map((d) => {
    const a = Math.min(1, Math.abs(d.pnl) / Math.max(...stats.days.map((x) => Math.abs(x.pnl)), 0.01));
    return `<i class="${d.pnl >= 0 ? "up" : "down"}" style="opacity:${(0.25 + 0.75 * a).toFixed(2)}" title="${esc(d.day)} ${esc(usd(d.pnl))}"></i>`;
  }).join("");
  const hour = (h) => `${String(h).padStart(2, "0")}:00`;
  return `
    <section class="mode-block lab-card">
      <h2>${esc(T("real"))}</h2>
      <p class="note faint">${esc(T("realNote", { m: stats.mode }))}</p>
      <div class="lab-tiles">
        ${tile(T("net"), usd(m.net), tone(m.net))}
        ${tile(T("trades"), m.trades)}
        ${tile(T("win"), `${n2(m.win_rate, 1)}%`)}
        ${tile(T("pf"), n2(m.profit_factor))}
        ${tile(T("expectancy"), usd(m.expectancy), tone(m.expectancy))}
        ${tile(T("dd"), pct(k.max_drawdown), "down")}
        ${tile(T("sharpe"), n2(k.sharpe))}
        ${tile(T("sortino"), n2(k.sortino))}
        ${tile(T("avgWin"), usd(m.avg_win), "up")}
        ${tile(T("avgLoss"), usd(m.avg_loss), "down")}
        ${tile(T("best"), usd(m.best), "up")}
        ${tile(T("worst"), usd(m.worst), "down")}
      </div>
      <p class="note">${esc(T("streak"))}: ${esc(T("streakTxt", { w: s.longest_wins, l: s.longest_losses, c: s.current > 0 ? `+${s.current}` : s.current }))}</p>
      ${days ? `<h3>${esc(T("days"))}</h3><div class="lab-days">${days}</div>` : ""}
    </section>
    <div class="lab-two">
      <section class="mode-block lab-card"><h2>${esc(T("books"))}</h2>${bars(stats.books, (b) => T(`bk_${b}`))}</section>
      <section class="mode-block lab-card"><h2>${esc(T("weekdays"))}</h2>${bars(stats.weekdays, (d) => d)}</section>
    </div>
    <div class="lab-two">
      <section class="mode-block lab-card"><h2>${esc(T("hours"))}</h2>${bars(stats.hours, hour)}</section>
      <section class="mode-block lab-card"><h2>${esc(T("symbols").replace(" (9.0)", ""))}</h2>${bars(stats.symbols, (x) => x)}</section>
    </div>`;
}

function render() {
  const body = $("labBody");
  if (!body) return;
  body.innerHTML = replayHtml() + realHtml() + `<p class="note faint lab-sources">${esc(T("sources"))}</p>`;
}

/* ------------------------------------------------------------------ data */

async function load() {
  try {
    [lab, stats] = await Promise.all([api("GET", "/api/lab"), api("GET", "/api/analytics").catch(() => null)]);
  } catch (err) {
    const body = $("labBody");
    if (body) body.innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
    return;
  }
  render();
  clearTimeout(poll);
  if (lab && lab.running) poll = setTimeout(load, 4000);
}

document.addEventListener("click", async (e) => {
  if (e.target.closest("#labRun")) {
    e.target.closest("#labRun").disabled = true;
    try { await api("POST", "/api/lab/run"); } catch (err) { alertLine(err.message); }
    load();
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "labEdge") {
    try { await api("POST", "/api/lab/edge", { on: e.target.checked }); } catch (err) { alertLine(err.message); }
    load();
  }
});

function alertLine(text) {
  const body = $("labBody");
  if (body) body.insertAdjacentHTML("afterbegin", `<p class="note warn">${esc(text)}</p>`);
}

window.addEventListener("mt:view", (e) => {
  view = e.detail;
  if (view === "lab") load();
});
window.addEventListener("mt:lang", () => { if (view === "lab") render(); });
