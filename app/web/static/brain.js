/* The Brain and the Swarm: what the research desk says about every stock, what
 * the news says right now, what the bot has learned — and ten strategy bots
 * evolving in parallel, with the one the real account actually trades with.
 *
 * Reads /api/brain and /api/swarm while their view is open; writes only the
 * brain's own settings (owner-only on the server).
 */

import { t, getLanguage } from "/i18n.js";

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
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

const locale = () => (getLanguage() === "tr" ? "tr-TR" : "en-US");
const num = (n, d = 0) => Number(n || 0).toLocaleString(locale(), { maximumFractionDigits: d, minimumFractionDigits: d });
const usd = (n) => (n === null || n === undefined) ? "—" : "$" + Number(n).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n, d = 0) => (n === null || n === undefined) ? "—" : (getLanguage() === "tr" ? "%" + num(n * 100, d) : num(n * 100, d) + "%");
const rText = (r) => (r === null || r === undefined) ? "—" : `${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(2)}R`;
const mood = (m) => (m === null || m === undefined) ? "—" : `${m >= 0 ? "+" : "−"}${Math.abs(m).toFixed(2)}`;
const tone = (x) => (x > 0 ? "up" : x < 0 ? "down" : "flat");
const ago = (sec) => {
  const s = Math.max(0, Date.now() / 1000 - sec);
  if (s < 3600) return t("brain.minAgo", { n: Math.floor(s / 60) });
  if (s < 172800) return t("brain.hourAgo", { n: Math.floor(s / 3600) });
  return t("brain.dayAgo", { n: Math.floor(s / 86400) });
};
const day = (sec) => new Date(sec * 1000).toLocaleDateString(locale(), { day: "numeric", month: "short" });

let brain = null;
let swarm = null;
let brainTab = "picks";
let openCard = null;
let view = "home";

/* ================================================================ brain */

async function loadBrain() {
  try {
    brain = await api("GET", "/api/brain");
    renderBrain();
  } catch (err) {
    $("brainBody").innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
  }
}

function renderBrain() {
  if (!brain) return;
  document.querySelectorAll("#brainTabs [data-brain-tab]").forEach((b) =>
    b.classList.toggle("on", b.dataset.brainTab === brainTab));
  const body = $("brainBody");
  if (brainTab === "news") body.innerHTML = newsTab();
  else if (brainTab === "learning") body.innerHTML = learningTab();
  else if (brainTab === "gates") body.innerHTML = gatesTab();
  else body.innerHTML = picksTab();
}

const DEC_ORDER = ["BUY_ZONE", "WAIT", "UNKNOWN", "AVOID"];

function picksTab() {
  const reports = Object.values(brain.reports || {}).sort((a, b) =>
    DEC_ORDER.indexOf(a.decision) - DEC_ORDER.indexOf(b.decision) || b.score - a.score);
  if (!reports.length) return `<div class="fl-card glow"><b>${esc(t("brain.waking"))}</b><p class="note">${esc(t("brain.wakingBody"))}</p></div>`;
  const found = new Set((brain.discovered || []).map((d) => d.symbol));
  return `
    ${moodCard(brain.radar, true)}
    <p class="note faint">${esc(t("brain.picksLead", { mode: t(`brain.mode.${brain.settings.quality_mode}`) }))}</p>
    <div class="fl-grid">${reports.map((r) => decisionCard(r, found.has(r.symbol))).join("")}</div>
    <p class="note faint">${esc(t("brain.picksSource"))}</p>`;
}

function verdictMark(v) { return { PASS: "✓", WATCH: "~", FAIL: "✕" }[v] || "—"; }

function decisionCard(r, found) {
  const m = (brain.radar.moods || {})[r.symbol] || {};
  const alt = (brain.alt || {})[r.symbol] || {};
  const open = openCard === r.symbol;
  const altParts = [];
  if (alt.attention) altParts.push(t("brain.attention", { x: alt.attention.toFixed(1) }));
  if (alt.insiders_30d !== null && alt.insiders_30d !== undefined) altParts.push(t("brain.insiders", { n: alt.insiders_30d }));
  if (alt.last_event) altParts.push(`8-K ${ago(alt.last_event.at)}`);
  if (alt.next_results) altParts.push(t("brain.results", { day: day(alt.next_results) }));
  const scale = r.value && r.price ? valueScale(r.price, r.value) : "";
  const flags = (brain.radar.flags || []).filter((f) => f.symbol === r.symbol);
  return `
    <article class="fl-card decision ${r.decision === "BUY_ZONE" ? "glow hot" : ""}" data-card="${esc(r.symbol)}">
      <header class="dc-head">
        <span class="ticker">${esc(r.symbol.slice(0, 4))}</span>
        <div class="dc-id"><b>${esc(r.symbol)}</b><span>${esc(r.fund ? t("brain.fund", { name: r.name }) : r.name)}</span></div>
        <div class="dc-word ${r.decision}"><b>${esc(t(`brain.dec.${r.decision}`))}</b><span>${num(r.score, 1)} / 5</span></div>
      </header>
      <div class="pills">${r.checks.map((c) => `
        <span class="pill ${c.verdict}"><i>${verdictMark(c.verdict)}</i>${esc(t(`brain.check.${c.kind}`))}</span>`).join("")}
      </div>
      ${scale}
      ${r.value && r.price ? `<p class="mono small">${esc(t("brain.priceValue", { price: usd(r.price), value: usd(r.value) }))} · ${esc(pvText(r.price_to_value))}</p>` : ""}
      <p class="small faint"><i class="mood-dot ${tone(m.mood || 0)}"></i>${esc(t("brain.newsLine", { mood: m.mood === null || m.mood === undefined ? t("brain.quiet") : mood(m.mood), n: m.count || 0 }))}</p>
      ${altParts.length ? `<p class="small alt">${esc(t("brain.altData"))} · ${esc(altParts.join(" · "))}</p>` : ""}
      ${found ? `<p class="small accent">★ ${esc(t("brain.found"))}</p>` : ""}
      ${flags.map((f) => `<span class="flag">⚑ ${esc(t(`brain.flag.${f.kind}`))}</span>`).join("")}
      ${open ? detail(r) : ""}
    </article>`;
}

function pvText(pv) {
  if (!pv) return "";
  const p = Math.round((pv - 1) * 100);
  return p > 0 ? t("brain.above", { p }) : p < 0 ? t("brain.below", { p: -p }) : t("brain.atValue");
}

function valueScale(price, value) {
  const lo = Math.min(price, value) * 0.8, hi = Math.max(price, value) * 1.1;
  const x = (v) => ((v - lo) / (hi - lo)) * 100;
  const a = x(Math.min(price, value)), b = x(Math.max(price, value));
  return `<div class="vscale"><i class="gap ${price <= value ? "up" : "down"}" style="left:${a}%;width:${b - a}%"></i>
    <i class="val" style="left:${x(value)}%"></i><i class="px" style="left:${x(price)}%"></i></div>`;
}

const METRIC = {
  PROFIT_YEARS: (f) => t("m.profitYears", { v: f.text }),
  REVENUE_GROWTH: (f) => t("m.revenue", { v: pct(f.value, 1) }),
  GROSS_MARGIN: (f) => t("m.gross", { v: pct(f.value) }),
  OPERATING_MARGIN: (f) => t("m.operating", { v: pct(f.value) }),
  RETURN_ON_EQUITY: (f) => t("m.roe", { v: pct(f.value) }),
  SHARE_CHANGE: (f) => t(f.value <= 0 ? "m.buyback" : "m.dilution", { v: pct(f.value, 1) }),
  DEBT_TO_PROFIT: (f) => t("m.debt", { v: num(f.value, 1) }),
  INTEREST_COVER: (f) => t("m.cover", { v: num(f.value) }),
  PRICE: (f) => t("m.price", { v: usd(f.value) }),
  VALUE: (f) => t("m.value", { v: usd(f.value) }),
  PRICE_TO_VALUE: (f) => pvText(f.value),
  VS_200_DAY: (f) => t("m.vs200", { v: pct(f.value - 1) }),
  DAILY_SWING: (f) => t("m.swing", { v: pct(f.value, 1) }),
  RED_FLAG: (f) => t(`brain.flag.${f.text}`),
  FUND: () => t("m.fund"),
};

function detail(r) {
  return `<div class="dc-detail">
    <b class="accent">${esc(t(`brain.line.${r.decision}`))}</b>
    ${r.checks.map((c, i) => `
      <div class="check-row"><span>${i + 1}. ${esc(t(`brain.q.${c.kind}`))}</span><b class="v-${c.verdict}">${esc(t(`brain.v.${c.verdict}`))}</b></div>
      ${(c.facts || []).map((f) => `<p class="fact">· ${esc((METRIC[f.metric] || (() => f.metric))(f))}</p>`).join("")}`).join("")}
    ${r.ai_read ? `<div class="ai-read"><b>${esc(t("brain.aiRead"))}</b><p>${esc(r.ai_read)}</p></div>` : ""}
    ${r.fiscal_year_end ? `<p class="small faint">${esc(t("brain.fy", { d: r.fiscal_year_end }))}</p>` : ""}
  </div>`;
}

function moodCard(radar, compact) {
  const m = radar.market;
  const angle = m === null || m === undefined ? 0 : Math.max(-1, Math.min(1, m)) * 90;
  const timeline = compact ? "" : sparkline(radar.timeline || []);
  return `<div class="fl-card mood ${m > 0.15 ? "glow" : ""}">
    <svg class="gauge" viewBox="0 0 120 66" aria-hidden="true">
      <defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stop-color="#ff5a4f"/><stop offset=".5" stop-color="#6b6450"/><stop offset="1" stop-color="#ffe01a"/></linearGradient></defs>
      <path d="M10 60 A50 50 0 0 1 110 60" stroke="url(#gg)" stroke-width="9" fill="none" stroke-linecap="round"/>
      ${m === null || m === undefined ? "" : `<g style="transform:rotate(${angle}deg);transform-origin:60px 60px;transition:transform .9s"><path d="M60 60 L60 18" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/></g><circle cx="60" cy="60" r="5" fill="#fff"/>`}
    </svg>
    <div><span class="label">${esc(t("brain.marketMood"))}</span>
      <b class="mood-word ${tone(m || 0)}">${esc(m === null || m === undefined ? t("brain.waitingNews") : moodName(m))}</b>
      <span class="mono small faint">${esc(mood(m))} · ${esc(t("brain.kept", { n: (radar.items || []).length, wire: radar.wire_size || 0 }))}</span></div>
    ${timeline}
  </div>`;
}

function moodName(m) {
  if (m >= 0.35) return t("brain.moodVeryGood");
  if (m >= 0.15) return t("brain.moodGood");
  if (m > -0.15) return t("brain.moodMixed");
  if (m > -0.35) return t("brain.moodBad");
  return t("brain.moodVeryBad");
}

function sparkline(values) {
  const pts = values.map((v, i) => (v === null ? null : [i * (300 / Math.max(values.length - 1, 1)), 30 - v * 26]));
  const path = pts.filter(Boolean).map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return `<svg class="spark-line" viewBox="0 0 300 60" preserveAspectRatio="none">
    <path d="M0 30 H300" class="zero"/>${path ? `<path d="${path}" class="line"/>` : ""}</svg>`;
}

function bar(v) {
  const x = Math.max(-1, Math.min(1, v || 0));
  const w = Math.abs(x) * 50;
  return `<span class="cbar"><i class="${x >= 0 ? "up" : "down"}" style="${x >= 0 ? `left:50%` : `left:${50 - w}%`};width:${w}%"></i></span>`;
}

function highlight(item) {
  const hits = new Map((item.hits || []).map((h) => [h.word, h.weight]));
  return esc(item.headline).replace(/[A-Za-z0-9'-]+/g, (word) => {
    const w = hits.get(word.toLowerCase());
    return w === undefined ? word : `<b class="${w > 0 ? "up" : "down"}">${word}</b>`;
  });
}

function newsTab() {
  const r = brain.radar;
  const moods = Object.entries(r.moods || {}).sort((a, b) => (b[1].mood ?? -9) - (a[1].mood ?? -9));
  return `
    ${moodCard(r, false)}
    <div class="fl-grid two">
      <div class="fl-card"><span class="label">${esc(t("brain.hot", { n: r.wire_size || 0 }))}</span>
        ${(r.hot || []).slice(0, 10).map((h) => `<div class="bar-row"><b class="mono">${esc(h.symbol)}</b>${bar(h.mood)}<span class="mono">${h.mentions}</span></div>`).join("") || `<p class="note faint">${esc(t("brain.noHot"))}</p>`}
        <p class="small faint">${esc(t("brain.hotNote"))}</p></div>
      <div class="fl-card"><span class="label">${esc(t("brain.byStock"))}</span>
        ${moods.map(([s, x]) => `<div class="bar-row"><b class="mono">${esc(s)}</b>${bar(x.mood)}<span class="mono ${tone(x.mood || 0)}">${esc(mood(x.mood))}</span><span class="mono faint">${x.count}</span></div>`).join("")}</div>
      <div class="fl-card"><span class="label">${esc(t("brain.topics"))}</span>
        ${(r.topics || []).slice(0, 9).map((x) => `<div class="bar-row"><span>${esc(t(`topic.${x.topic}`))}</span><span class="mono">${x.count}</span><span class="mono ${tone(x.mood)}">${esc(mood(x.mood))}</span></div>`).join("") || `<p class="note faint">—</p>`}</div>
      ${(r.flags || []).length ? `<div class="fl-card danger"><span class="label">${esc(t("brain.flags"))}</span>
        ${r.flags.slice(0, 8).map((f) => `<p><b>⚑ ${esc(f.symbol)} · ${esc(t(`brain.flag.${f.kind}`))}</b><br><span class="small">${esc(f.headline)}</span></p>`).join("")}</div>` : ""}
    </div>
    <span class="label">${esc(t("brain.wire", { n: (r.items || []).length, ai: r.ai_read || 0 }))}</span>
    <div class="wire">${(r.items || []).map((n) => `
      <div class="wire-row"><span class="mono faint">${esc(ago(n.created_at))}</span>
        <span class="mono accent">${esc((n.symbols || []).slice(0, 4).join(" "))}</span>
        <p>${highlight(n)}</p>
        <span class="mono ${tone(n.mood)}">${n.ai_score !== null && n.ai_score !== undefined ? "AI " : ""}${esc(mood(n.mood))}</span></div>`).join("")}</div>`;
}

function learningTab() {
  const b = brain;
  const won = b.shadow_closed ? Math.round((b.shadow_wins / b.shadow_closed) * 100) : null;
  return `
    <div class="fl-card glow">
      <span class="label">${esc(t("brain.learnTitle"))}</span>
      <div class="stats">
        <div><b>${b.shadow_closed}</b><span>${esc(t("brain.resultsLabel"))}</span></div>
        <div><b>${won === null ? "—" : (getLanguage() === "tr" ? "%" + won : won + "%")}</b><span>${esc(t("brain.won"))}</span></div>
        <div><b class="${tone(b.shadow_avg_r || 0)}">${esc(rText(b.shadow_avg_r))}</b><span>${esc(t("brain.average"))}</span></div>
        <div><b class="accent">${(b.rules || []).length}</b><span>${esc(t("brain.rules"))}</span></div>
      </div>
      <p class="note faint">${esc(t("brain.learnBody", { n: b.real_results }))}</p>
    </div>
    <div class="fl-grid two">
      <div class="fl-card"><span class="label accent">${esc(t("brain.rulesTitle"))}</span>
        ${(b.rules || []).map((r) => `<p><b>✕ ${esc(r.key)} ${esc(r.value)}</b><br><span class="small">${esc(t("brain.ruleLine", { n: num(r.n), w: num(r.win_rate * 100), r: rText(r.avg_r) }))}</span></p>`).join("")
          || `<p class="note faint">${esc(t("brain.noRules"))}</p>`}</div>
      <div class="fl-card"><span class="label">${esc(t("brain.lessons"))}</span>
        ${(b.lessons || []).map((l) => `<div class="bar-row"><span>${esc(l.key)} ${esc(l.value)}</span>${bar(l.shrunk)}<span class="mono ${tone(l.shrunk)}">${esc(rText(l.shrunk))}</span><span class="mono faint">${num(l.n)}</span></div>`).join("")
          || `<p class="note faint">${esc(t("brain.noLessons"))}</p>`}</div>
    </div>
    <div class="fl-card"><span class="label">${esc(t("brain.following"))}</span>
      ${[...(b.shadow_open || []), ...(b.shadow_recent || [])].slice(0, 16).map((s) => `
        <div class="bar-row"><b class="mono">${esc(s.symbol)}</b><span class="mono small">${esc(usd(s.entry))} · stop ${esc(usd(s.stop))} · ${esc(t("brain.target"))} ${esc(usd(s.target))}</span>
        <span class="small ${s.bought ? "accent" : "faint"}">${esc(s.bought ? t("brain.bought") : t("brain.inHead"))}${s.exit ? " · " + esc(s.exit) : ""}</span>
        <span class="mono ${tone(s.r || 0)}">${s.r === null || s.r === undefined ? "…" : esc(rText(s.r))}</span></div>`).join("") || `<p class="note faint">${esc(t("brain.noShadows"))}</p>`}
    </div>
    <button class="ghost danger-text" data-brain-forget>${esc(t("brain.forget"))}</button>`;
}

function gatesTab() {
  const s = brain.settings;
  const toggle = (key, title, hint) => `
    <label class="gate"><input type="checkbox" data-brain-set="${key}" ${s[key] ? "checked" : ""}>
      <span class="switch"></span><span><b>${esc(t(title))}</b><small>${esc(t(hint))}</small></span></label>`;
  return `<div class="fl-card">
      <span class="label">${esc(t("brain.picky"))}</span>
      <div class="seg-row">${["STRICT", "BALANCED", "OFF"].map((m) => `
        <button class="seg ${s.quality_mode === m ? "active" : ""}" data-brain-mode="${m}">${esc(t(`brain.mode.${m}`))}</button>`).join("")}</div>
      <p class="note faint">${esc(t(`brain.modeHint.${s.quality_mode}`))}</p>
      ${toggle("news_check", "brain.g.news", "brain.g.newsHint")}
      ${toggle("learning", "brain.g.learn", "brain.g.learnHint")}
      ${toggle("ai_check", "brain.g.ai", "brain.g.aiHint")}
      ${toggle("discover", "brain.g.discover", "brain.g.discoverHint")}
      ${toggle("self_improve", "brain.g.evolve", "brain.g.evolveHint")}
    </div>`;
}

/* ================================================================ swarm */

async function loadSwarm() {
  try {
    swarm = await api("GET", "/api/swarm");
    renderSwarm();
  } catch (err) {
    $("swarmBody").innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
  }
}

let shownTested = 0;

function renderSwarm() {
  const s = swarm;
  if (!s) return;
  const set = s.settings || {};
  const running = s.running;
  const leaderboard = [...(s.bots || [])].sort((a, b) => ((b.valid || {}).expectancy ?? -9) - ((a.valid || {}).expectancy ?? -9));
  $("swarmBody").innerHTML = `
    <section class="fl-hero ${running ? "live" : ""}">
      <div class="hero-left">
        <span class="label accent"><i class="pulse ${running ? "on" : ""}"></i>${esc(t(running ? "swarm.mining" : "swarm.idle", { n: (s.bots || []).length }))}</span>
        <div class="mega" id="swarmTested">${num(shownTested || s.tested)}</div>
        <span class="faint">${esc(t("swarm.tested"))}</span>
        <div class="stats">
          <div><b>${num(s.rate)}</b><span>${esc(t("swarm.perSecond"))}</span></div>
          <div><b>${num(s.generations)}</b><span>${esc(t("swarm.generations"))}</span></div>
          <div><b class="accent">v${s.version}</b><span>${esc(t("swarm.strategy"))}</span></div>
          <div><b>${s.cpus || "—"}</b><span>${esc(t("swarm.cores"))}</span></div>
        </div>
        <p class="small faint">${esc(t("swarm.data", { n: s.symbols, bars: num(s.bars) }))}</p>
      </div>
      <div class="hero-right">
        <span class="label">${esc(t("swarm.bots"))}</span>
        <div class="bot-count">${[0, 2, 4, 6, 8, 10].map((n) => `<button class="seg ${set.bots === n ? "active" : ""}" data-swarm-bots="${n}">${n}</button>`).join("")}</div>
        <span class="label">${esc(t("swarm.power"))}</span>
        <div class="seg-row">
          <button class="seg ${set.power === "full" ? "active" : ""}" data-swarm-power="full">${esc(t("swarm.full"))}</button>
          <button class="seg ${set.power === "light" ? "active" : ""}" data-swarm-power="light">${esc(t("swarm.light"))}</button>
        </div>
        <p class="small warn">${esc(t("swarm.ramWarning"))}</p>
      </div>
    </section>
    ${champion(s)}
    <span class="label">${esc(t("swarm.leaderboard"))}</span>
    <div class="bots">${leaderboard.map((b, i) => botCard(b, i)).join("") || `<p class="note faint">${esc(t("swarm.noBots"))}</p>`}</div>
    <span class="label">${esc(t("swarm.changes"))}</span>
    ${(s.history || []).map(promotion).join("") || `<p class="note faint">${esc(t("swarm.noChanges"))}</p>`}
    <p class="note faint">${esc(t("swarm.honest", s.rules || {}))}</p>
    ${s.champion && s.champion.label !== s.default.label ? `<button class="ghost danger-text" data-swarm-reset>${esc(t("swarm.reset"))}</button>` : ""}`;
  animateCounter(s.tested);
}

function animateCounter(target) {
  const el = $("swarmTested");
  if (!el) return;
  const from = shownTested || target;
  const started = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - started) / 1800);
    shownTested = Math.round(from + (target - from) * k);
    el.textContent = num(shownTested);
    if (k < 1 && view === "swarm") requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function champion(s) {
  const c = s.champion, d = s.default;
  const gene = (label, now, orig) => `<div class="gene"><span>${esc(label)}</span><b class="${now !== orig ? "accent" : ""}">${esc(now)}</b><span class="faint">${esc(orig)}</span></div>`;
  const ct = s.champion_test, dt = s.default_test;
  const fam = (g) => t(`swarm.family.${g.family}`);
  return `<section class="fl-card glow champion">
    <div class="ch-head"><span class="label">${esc(t("swarm.tradingWith"))}</span><span class="tag">${c.label === d.label ? esc(t("swarm.original")) : "v" + s.version}</span></div>
    <b class="ch-label">${esc(c.label)}</b>
    <div class="genes">
      <div class="gene head"><span></span><span>${esc(t("swarm.now"))}</span><span>${esc(t("swarm.orig"))}</span></div>
      ${gene(t("swarm.g.family"), fam(c), fam(d))}
      ${gene(t("swarm.g.averages"), `${c.fast} / ${c.slow}`, `${d.fast} / ${d.slow}`)}
      ${gene(t("swarm.g.entry"), num(c.entry_rsi), num(d.entry_rsi))}
      ${gene(t("swarm.g.exit"), num(c.exit_rsi), num(d.exit_rsi))}
      ${gene(t("swarm.g.stop"), num(c.atr_mult, 2), num(d.atr_mult, 2))}
      ${gene(t("swarm.g.target"), num(c.reward_risk, 2) + ":1", num(d.reward_risk, 2) + ":1")}
    </div>
    <span class="label">${esc(t("swarm.unseen"))}</span>
    <div class="gene"><span>${esc(t("swarm.now"))}</span><b class="${tone(ct ? ct.expectancy : 0)}">${ct ? esc(rText(ct.expectancy)) : "—"}</b><span class="faint">${ct ? esc(t("swarm.wonOf", { w: pct(ct.win_rate), n: ct.trades })) : ""}</span></div>
    <div class="gene"><span>${esc(t("swarm.orig"))}</span><b class="${tone(dt ? dt.expectancy : 0)}">${dt ? esc(rText(dt.expectancy)) : "—"}</b><span class="faint">${dt ? esc(t("swarm.wonOf", { w: pct(dt.win_rate), n: dt.trades })) : ""}</span></div>
  </section>`;
}

function botCard(b, rank) {
  const live = b.live || {};
  const v = b.valid, c = b.confirm;
  return `<article class="bot ${rank === 0 && v ? "lead" : ""}">
    <header><span class="rank">#${rank + 1}</span><b>${esc(b.name)}</b><span class="tag">${esc(t(`swarm.family.${b.family}`))}</span></header>
    <div class="bot-stats"><span class="mono">${num(b.tested)}</span><span class="faint">${esc(t("swarm.tested"))}</span>
      <span class="mono">${num(b.rate)}/s</span></div>
    <p class="small mono">${esc(b.best ? b.best.label : t("swarm.warming"))}</p>
    <div class="bot-scores">
      <div><span class="faint">${esc(t("swarm.train"))}</span><b class="${tone(b.train ? b.train.expectancy : 0)}">${b.train ? esc(rText(b.train.expectancy)) : "—"}</b></div>
      <div><span class="faint">${esc(t("swarm.valid"))}</span><b class="${tone(v ? v.expectancy : 0)}">${v ? esc(rText(v.expectancy)) : "—"}</b></div>
      <div><span class="faint">${esc(t("swarm.confirm"))}</span><b class="${tone(c ? c.expectancy : 0)}">${c ? esc(rText(c.expectancy)) : "—"}</b></div>
      <div><span class="faint">${esc(t("swarm.paper"))}</span><b class="${tone(live.sum_r || 0)}">${esc(rText(live.sum_r || 0))}</b></div>
    </div>
    <p class="small faint">${esc(t("swarm.paperLine", { open: (live.open || []).length, trades: live.trades || 0 }))}</p>
  </article>`;
}

function promotion(p) {
  return `<article class="fl-card ${p.rollback ? "danger" : "accent-border"}">
    <div class="ch-head"><b class="${p.rollback ? "down" : "accent"}">${esc(p.rollback ? t("swarm.rolledBack", { v: p.version }) : t("swarm.improved", { bot: p.bot, v: p.version }))}</b>
      <span class="mono faint">${esc(new Date(p.at * 1000).toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))}</span></div>
    <p class="mono small">${esc(p.after.label)}</p>
    <p class="small ${tone(p.unseen_after - p.unseen_before)}">${esc(t("swarm.unseenLine", { a: rText(p.unseen_before), b: rText(p.unseen_after), n: p.trades }))}</p>
  </article>`;
}

/* =============================================================== wiring */

document.addEventListener("click", async (e) => {
  const tab = e.target.closest("[data-brain-tab]");
  if (tab) { brainTab = tab.dataset.brainTab; renderBrain(); return; }
  const card = e.target.closest("[data-card]");
  if (card && view === "brain") { openCard = openCard === card.dataset.card ? null : card.dataset.card; renderBrain(); return; }
  const mode = e.target.closest("[data-brain-mode]");
  if (mode) { await setBrain({ quality_mode: mode.dataset.brainMode }); return; }
  if (e.target.closest("[data-brain-forget]")) {
    if (confirm(t("brain.forgetConfirm"))) { await api("POST", "/api/brain/forget").catch(() => {}); loadBrain(); }
    return;
  }
  const bots = e.target.closest("[data-swarm-bots]");
  if (bots) { await setBrain({ bots: Number(bots.dataset.swarmBots) }); loadSwarm(); return; }
  const power = e.target.closest("[data-swarm-power]");
  if (power) { await setBrain({ power: power.dataset.swarmPower }); loadSwarm(); return; }
  if (e.target.closest("[data-swarm-reset]")) {
    if (confirm(t("swarm.resetConfirm"))) { await api("POST", "/api/swarm/reset").catch(() => {}); loadSwarm(); }
  }
});

document.addEventListener("change", async (e) => {
  const box = e.target.closest("[data-brain-set]");
  if (box) await setBrain({ [box.dataset.brainSet]: box.checked });
});

async function setBrain(changes) {
  try {
    const r = await api("POST", "/api/brain/settings", changes);
    if (brain) { brain.settings = r.settings; renderBrain(); }
  } catch (err) {
    window.showAlert?.({ tone: "bad", title: err.message });
  }
}

let timer = null;
window.addEventListener("mt:view", (e) => {
  view = e.detail;
  clearInterval(timer);
  if (view === "brain") { loadBrain(); timer = setInterval(loadBrain, 15000); }
  if (view === "swarm") { loadSwarm(); timer = setInterval(loadSwarm, 2500); }
});
window.addEventListener("mt:lang", () => { if (view === "brain") renderBrain(); if (view === "swarm") renderSwarm(); });
window.addEventListener("mt:ws", (e) => {
  const type = e.detail.type;
  if (type === "brain_promotion" || type === "brain_found") {
    window.showAlert?.({ tone: "good", title: e.detail.title || "", body: e.detail.text || "" });
  }
});
