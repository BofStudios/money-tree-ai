/* Launched from the phone's home screen, the app opens at the manifest's bare
   start_url and the ?token= from the first visit is gone. So the token is
   remembered on this device the first time it arrives in the URL. */
const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("token");
  try {
    if (fromUrl) localStorage.setItem("mt_token", fromUrl);
    return fromUrl || localStorage.getItem("mt_token") || "";
  } catch {
    return fromUrl || "";
  }
})();
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);
const $ = (id) => document.getElementById(id);
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

let state = {};
let runConfig = null;
let pickStake = null;
let pickMult = null;
let selected = null;
let activeView = "home";
let lastQuote = null;
let claudeReady = false;
let aiMemory = [];

/* Said once, in the two places it is needed, so the advice cannot drift apart. */
const NO_AI_HELP = [
  "No AI is connected yet, so I can only narrate — I cannot answer freely.",
  "",
  "Any one of these fixes it, and the first three cost nothing:",
  "",
  "1. Ollama — runs on this PC, no account at all. Install it from ollama.com,",
  "   run \"ollama pull llama3.2\", and restart me.",
  "2. Gemini — free key at aistudio.google.com/apikey, then GEMINI_API_KEY in .env.",
  "3. Groq — free key at console.groq.com/keys, then GROQ_API_KEY in .env.",
  "4. Claude — paid, and the strongest. ANTHROPIC_API_KEY in .env.",
].join("\n");

function renderMemory() {
  const host = $("memoryList");
  if (!host) return;
  $("memoryCount").textContent = aiMemory.length;
  $("memoryBox").hidden = aiMemory.length === 0;
  host.innerHTML = aiMemory
    .map((f, i) => `<li>${escapeHtml(f.text)}<button data-forget="${i}" aria-label="Forget">×</button></li>`)
    .join("");
}

/* ================================================================ helpers */

const money = (n, d = 2) =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const signed = (n, d = 2) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : (n >= 0 ? "+" : "") + money(n, d);

const pct = (n) => (n === null || n === undefined ? "—" : `${signed(n)}%`);
const cur = () => (runConfig && runConfig.currency === "USD" ? "$" : "");

function tone(el, n) {
  if (!el) return;
  el.classList.remove("up", "down");
  if (n > 0) el.classList.add("up");
  else if (n < 0) el.classList.add("down");
}

const stamp = (iso) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/* Counts a figure from its old value to its new one instead of snapping. */
const counters = new Map();
function setNumber(el, value, format = (v) => money(v)) {
  if (!el) return;
  const key = el.id || el;
  const from = counters.get(key);
  counters.set(key, value);

  if (from === undefined || from === value || Number.isNaN(value)) {
    el.textContent = format(value);
    return;
  }

  el.classList.remove("bump");
  void el.offsetWidth;
  el.classList.add("bump");

  const start = performance.now();
  const span = 520;
  const step = (now) => {
    const p = Math.min((now - start) / span, 1);
    // ease-out so it decelerates into the final figure
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = format(from + (value - from) * eased);
    if (p < 1) requestAnimationFrame(step);
    else el.textContent = format(value);
  };
  requestAnimationFrame(step);
}

const clock = () => new Date().toLocaleTimeString([], { hour12: false });

/* ================================================================== clocks */

function tickClock() {
  $("clockNY").textContent = new Intl.DateTimeFormat("en-GB", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date()) + " NY";
}
setInterval(tickClock, 1000);
tickClock();

function tickCountdown() {
  const m = state.market;
  if (!m) return;
  const target = m.is_open ? m.next_close : m.next_open;
  if (!target) return;
  const left = Math.max(0, (new Date(target) - new Date()) / 1000);
  const d = Math.floor(left / 86400);
  const h = Math.floor((left % 86400) / 3600);
  const mi = Math.floor((left % 3600) / 60);
  const s = Math.floor(left % 60);
  $("marketDetail").textContent = d ? `${d}d ${h}h` : h ? `${h}h ${mi}m` : `${mi}m ${s}s`;
}
setInterval(tickCountdown, 1000);

const WEEKDAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function renderMarket(m) {
  $("marketLed").className = "dot " + (m.is_open ? "open" : "closed");
  if (m.is_open) {
    $("marketHeadline").textContent = "Market open";
  } else if (m.next_open) {
    const when = new Date(m.next_open);
    const ist = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(when);
    $("marketHeadline").textContent = `Closed until ${WEEKDAY[when.getDay()]} ${ist}`;
  } else {
    $("marketHeadline").textContent = "Market closed";
  }
  tickCountdown();
}

/* =================================================================== chart */

const t = { text2: css("--text-2"), line: css("--line-soft"), up: css("--up"), down: css("--down"), text: css("--text") };

const chart = LightweightCharts.createChart($("chart"), {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: t.text2, fontSize: 11, attributionLogo: false },
  grid: { vertLines: { color: t.line }, horzLines: { color: t.line } },
  rightPriceScale: { borderVisible: false },
  timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
});

const candleSeries = chart.addCandlestickSeries({
  upColor: t.up, downColor: t.down,
  borderUpColor: t.up, borderDownColor: t.down,
  wickUpColor: t.up, wickDownColor: t.down,
});

const overlayColors = ["#7d8590", "#4a4f57"];
const overlaySeries = new Map();
let priceLines = [];

function drawPositionLines(position) {
  priceLines.forEach((l) => candleSeries.removePriceLine(l));
  priceLines = [];
  if (!position) return;
  const add = (price, color, title) => {
    if (!price) return;
    priceLines.push(candleSeries.createPriceLine({
      price, color, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title,
    }));
  };
  add(position.entry_price, t.text, "entry");
  add(position.stop_loss, t.down, "stop");
  add(position.take_profit, t.up, "target");
}

const spark = LightweightCharts.createChart($("equitySpark"), {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: t.text2, fontSize: 9, attributionLogo: false },
  grid: { vertLines: { visible: false }, horzLines: { visible: false } },
  rightPriceScale: { visible: false }, leftPriceScale: { visible: false },
  timeScale: { visible: false },
  crosshair: { horzLine: { visible: false }, vertLine: { visible: false } },
  handleScroll: false, handleScale: false,
});
const sparkSeries = spark.addAreaSeries({
  lineColor: t.text, topColor: "rgba(255,255,255,0.14)", bottomColor: "rgba(255,255,255,0)",
  lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false,
});

/* ==================================================================== nav */

function showView(name) {
  activeView = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  window.scrollTo({ top: 0, behavior: "instant" });
  // On a phone the tab bar scrolls sideways; keep the chosen tab in view.
  const bar = $("nav");
  const tab = bar && bar.querySelector(`.tab[data-tab="${name}"]`);
  if (tab && bar.scrollWidth > bar.clientWidth) {
    // Instant, not smooth: smooth scrolling is driven by animation frames and
    // silently does nothing when the page is backgrounded or throttled.
    bar.scrollLeft = tab.offsetLeft - (bar.clientWidth - tab.offsetWidth) / 2;
  }
  if (name === "chart" && selected) loadChart(selected).catch(() => {});
  if (name === "live") loadSetup().catch(() => {});
  if (name === "catalysts") loadCatalysts().catch(() => {});
  if (name === "news") loadNews().catch(() => {});
}

$("nav").onclick = (e) => {
  const tab = e.target.closest(".tab");
  if (tab) showView(tab.dataset.tab);
};

/* The rail is always on screen on desktop; on a phone it slides up as a sheet. */
function openAI(open) {
  $("aiRail").classList.toggle("open", open);
  if (open) {
    $("aiPing").hidden = true;
    scrollChat(true);
    setTimeout(() => $("askInput").focus(), 350);
  }
}
$("aiOpen").onclick = () => openAI(true);
$("aiClose").onclick = () => openAI(false);

/* ==================================================================== chat */

const seen = new Set();

function addMessage({ text, level = "think", time, from = "bot" }) {
  const wrap = document.createElement("div");
  wrap.className = `msg from-${from} lvl-${level}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = time || clock();

  wrap.append(bubble, meta);
  $("chat").appendChild(wrap);
  while ($("chat").children.length > 250) $("chat").removeChild($("chat").firstChild);
  scrollChat();

  const notable = ["signal", "action", "warn", "result"].includes(level);
  if (from === "bot" && notable && !$("aiRail").classList.contains("open")) {
    $("aiPing").hidden = false;
  }
}

function scrollChat(force = false) {
  // The rail scrolls itself; the page never moves for a new message.
  const el = $("chat");
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
  if (force || nearBottom) el.scrollTop = el.scrollHeight;
}

let typingEl = null;
function showTyping(on) {
  if (on && !typingEl) {
    typingEl = document.createElement("div");
    typingEl.className = "msg from-bot";
    typingEl.innerHTML = '<div class="bubble"><div class="typing"><i></i><i></i><i></i></div></div>';
    $("chat").appendChild(typingEl);
    scrollChat(true);
  } else if (!on && typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

function pushLine(line) {
  const key = `${line.time}|${line.text}`;
  if (seen.has(key)) return;
  seen.add(key);
  addMessage({ text: line.text, level: line.level, time: line.clock });
}

const SUGGESTIONS = [
  "How are we doing?",
  "Why no trades?",
  "Explain the last trade",
  "Is the strategy working?",
];
$("suggestions").innerHTML = SUGGESTIONS.map((s) => `<button class="suggestion" type="button">${s}</button>`).join("");
$("suggestions").onclick = (e) => {
  const b = e.target.closest(".suggestion");
  if (!b) return;
  $("askInput").value = b.textContent;
  $("askForm").requestSubmit();
};

/* ===================================================================== run */

function renderRun(challenge) {
  const host = $("runBody");
  if (!runConfig || runConfig.enabled === false) { host.innerHTML = ""; return; }

  if (challenge && challenge.active) {
    const wasLive = host.dataset.live === "1";
    host.className = "run";
    host.dataset.live = "1";
    if (wasLive) {
      // Already on screen: move the numbers rather than rebuilding the block,
      // otherwise the counter restarts and the bar jumps.
      setNumber($("runValue"), challenge.value, (v) => cur() + money(v));
      const bar = $("runFill");
      if (bar) bar.style.width = `${challenge.progress_pct}%`;
      const meta = $("runPct");
      if (meta) meta.textContent = `${challenge.progress_pct}%`;
      const trades = $("runTrades");
      if (trades) {
        trades.textContent = `${challenge.trades} trade${challenge.trades === 1 ? "" : "s"}`
          + (challenge.win_rate === null ? "" : ` · ${challenge.win_rate}% won`);
      }
      return;
    }
    host.innerHTML = liveRun(challenge);
    return;
  }
  host.dataset.live = "0";
  const last = (runConfig.history || [])[0];
  host.className = "run" + (last ? ` ${last.status}` : "");
  host.innerHTML = picker(last);
  paintPicker();
}

function liveRun(c) {
  const $$ = cur();
  // Same money as the account above it, so it carries the same label.
  const kind = state.mode === "live" ? "real money" : "practice money";
  return `
    <div class="run-label">The run<span class="run-kind">${kind}</span></div>
    <div class="run-value" id="runValue">${$$}${money(c.value)}</div>
    <div class="run-of">of ${$$}${money(c.target)} target · started at ${$$}${money(c.stake)}</div>
    <div class="run-bar"><i id="runFill" style="width:${c.progress_pct}%"></i></div>
    <div class="run-meta">
      <span id="runPct">${c.progress_pct}%</span>
      <span id="runTrades">${c.trades} trade${c.trades === 1 ? "" : "s"}${c.win_rate === null ? "" : ` · ${c.win_rate}% won`}</span>
      <span>stops at ${$$}${money(c.bust_floor)}</span>
    </div>
    <div class="run-actions">
      <button id="btnRunStop" class="small">Stop the run</button>
    </div>`;
}

function picker(last) {
  const $$ = cur();
  const verdict = !last ? "" : `<p class="note">${
    last.status === "won"
      ? `Last run made it: ${$$}${money(last.stake)} → ${$$}${money(last.value)} in ${last.trades} trades.`
      : last.status === "lost"
        ? `Last run ran out at ${$$}${money(last.value)} after ${last.trades} trades.`
        : `Last run stopped at ${$$}${money(last.value)}.`
  }</p>`;

  const amounts = runConfig.presets
    .map((v) => `<button class="chip" data-stake="${v}">${$$}${v % 1 ? v.toFixed(2) : v}</button>`).join("");
  const mults = runConfig.multipliers
    .map((m) => `<button class="chip" data-mult="${m}">${m}×</button>`).join("");

  return `
    <div class="run-label">The run</div>
    <div class="run-value" id="pickTitle">—</div>
    <div class="run-of">Give the bot a stake and a target. It trades only this money.</div>
    ${verdict}
    <div class="pick">
      <div class="pick-row">
        <span class="pick-label">Stake</span>
        <div class="chips">${amounts}</div>
      </div>
      <div class="pick-row">
        <span class="pick-label">Target</span>
        <div class="chips">${mults}</div>
      </div>
      <p class="note" id="pickOdds"></p>
      <div class="run-actions">
        <button class="solid" id="btnRunStart">Start</button>
        <span class="muted">Paper money</span>
      </div>
    </div>`;
}

function paintPicker() {
  if (pickStake === null) pickStake = runConfig.default_stake;
  if (pickMult === null) pickMult = runConfig.default_multiplier;

  document.querySelectorAll("[data-stake]").forEach((b) =>
    b.classList.toggle("on", Number(b.dataset.stake) === pickStake));
  document.querySelectorAll("[data-mult]").forEach((b) =>
    b.classList.toggle("on", Number(b.dataset.mult) === pickMult));

  const target = pickStake * pickMult;
  const title = $("pickTitle");
  if (title) title.innerHTML = `${cur()}${money(pickStake)} <span class="arrow">→</span> <span class="to">${cur()}${money(target)}</span>`;
  refreshOdds(pickStake, target);
}

async function refreshOdds(stake, target) {
  const host = $("pickOdds");
  if (!host) return;
  try {
    const o = await post("/api/challenge/odds", { stake, target });
    host.textContent = o.winning_trades_needed
      ? `Each win adds ${o.take_profit_pct}%, each loss takes ${o.stop_loss_pct}%. `
        + `That is roughly ${o.winning_trades_needed} winning trades in a row — a long shot. `
        + `The run ends by itself at ${cur()}${money(o.bust_floor)}.`
      : "This target cannot be reached with the current settings.";
  } catch { host.textContent = ""; }
}

/* ============================================================== catalysts */

const CONVICTION = { high: "●●●", medium: "●●○", low: "●○○" };

function renderCatalysts(data) {
  const rows = data.catalysts || [];
  $("catalystEmpty").style.display = rows.length ? "none" : "block";
  $("catalystDot").hidden = !rows.some((c) => c.in_entry_window && c.status !== "holding");

  $("catalystList").innerHTML = rows.map((c) => {
    const days = c.days_away;
    const unit = days === 0 ? "today" : Math.abs(days) === 1 ? "day" : "days";
    const open = c.in_entry_window && c.status !== "holding";
    const cls = c.is_past ? "past" : open ? "open" : "";

    const state = c.status === "holding"
      ? '<span class="cat-state holding">holding</span>'
      : open
        ? '<span class="cat-state open">entry window open</span>'
        : c.is_past
          ? '<span class="cat-state">event passed</span>'
          : `<span class="cat-state">opens in ${c.window_opens_in}d</span>`;

    return `<div class="cat ${cls}">
      <div class="cat-when">
        <span class="cat-days">${days === 0 ? "0" : Math.abs(days)}</span>
        <span class="cat-unit">${unit}${days < 0 ? " ago" : ""}</span>
      </div>
      <div class="cat-main">
        <div class="cat-title">${escapeHtml(c.title)}</div>
        <div class="cat-meta">
          <span>${c.symbol}</span>
          <span>${c.event_date}</span>
          <span>${c.date_confidence}</span>
          <span>${CONVICTION[c.conviction] || ""}</span>
          <span>${c.exit_rule === "before" ? "sell into it" : "hold through"}</span>
        </div>
        ${c.thesis ? `<div class="cat-thesis">${escapeHtml(c.thesis)}</div>` : ""}
        ${state}
      </div>
      <div class="cat-actions">
        ${c.status === "holding"
          ? `<button class="small" data-cat-status="${c.id}" data-to="closed">Closed</button>`
          : `<button class="small" data-cat-status="${c.id}" data-to="holding">I'm in</button>`}
        <button class="small ghost" data-cat-del="${c.id}">Remove</button>
      </div>
    </div>`;
  }).join("");

  const news = data.news || [];
  $("newsEmpty").style.display = news.length ? "none" : "block";
  if (!data.news_available) {
    $("newsEmpty").textContent =
      "Headlines need broker keys in .env — the same ones the bot already uses for prices.";
  }
  $("newsList").innerHTML = news.map((n) => `
    <a class="news-item" href="${n.url}" target="_blank" rel="noopener">
      <div class="news-head">${escapeHtml(n.headline)}</div>
      <div class="news-meta">
        <span>${stamp(n.created_at)}</span>
        <span>${escapeHtml(n.source)}</span>
        <span class="news-syms">${n.symbols.slice(0, 5).join(" ")}</span>
      </div>
    </a>`).join("");

  $("catalystWarning").textContent = rows.length
    ? "Events are not free money. A date everyone knows is already in the price, stocks "
      + "often peak before the day and fall on it, and a delay can undo the whole thesis. "
      + "Treat this as a calendar, not a signal."
    : "";
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

async function loadCatalysts() {
  renderCatalysts(await get("/api/catalysts"));
}

$("btnAddCatalyst").onclick = () => {
  const form = $("catalystForm");
  form.hidden = !form.hidden;
  if (!form.hidden) $("cTitle").focus();
};
$("btnCancelCatalyst").onclick = () => { $("catalystForm").hidden = true; };

$("catalystForm").onsubmit = async (e) => {
  e.preventDefault();
  const body = {
    title: $("cTitle").value.trim(),
    symbol: $("cSymbol").value.trim().toUpperCase(),
    event_date: $("cDate").value.trim(),
    thesis: $("cThesis").value.trim(),
    conviction: $("cConviction").value,
    entry_days_before: Number($("cWindow").value),
    exit_rule: $("cExit").value,
    date_confidence: $("cConfidence").value,
  };
  try {
    await post("/api/catalysts", body);
    $("catalystForm").reset();
    $("catalystForm").hidden = true;
    await loadCatalysts();
  } catch (err) {
    alert(err.message);
  }
};

/* ================================================================= render */

/* Says plainly whose money the big number on screen is. A simulated balance
   that looks identical to a real one is the easiest way to mislead someone,
   so paper and signal modes are labelled every time the status refreshes. */
function renderRealCheck(s) {
  const box = $("realCheck");
  const armed = s.risk && s.risk.armed;

  const card = {
    paper: {
      cls: "practice",
      tag: "Practice money",
      body: `You have not deposited anything. The bot is trading <b>pretend money</b>
             against real live prices so you can watch how it behaves before any of
             your own money is involved. Nothing here can be withdrawn.`,
      line: ["Your real money at risk", "$0.00"],
    },
    signal: {
      cls: "practice",
      tag: "Midas mode · scorecard only",
      body: `The bot holds no money. Your money is in <b>Midas</b>, where only you can
             move it. The figure above is a running score of what its calls would have
             made, so you can judge them before you follow one.`,
      line: ["Money the bot controls", "$0.00"],
    },
    live: {
      cls: "livemoney",
      tag: armed ? "Real money · armed" : "Real money · not armed",
      body: armed
        ? `This is your <b>real money</b> and the bot is allowed to place
           orders with it. Losses here are real.`
        : `This is your <b>real money</b>. The bot is watching but not
           allowed to place orders until you arm it.`,
      line: ["Your real money at risk", "$" + money(s.equity)],
    },
  }[s.mode];

  if (!card) { box.hidden = true; return; }

  box.hidden = false;
  box.className = "realcheck " + card.cls;
  box.innerHTML = `
    <span class="rc-tag"><i></i>${card.tag}</span>
    <p class="rc-body">${card.body}</p>
    <div class="rc-line"><span>${card.line[0]}</span><b>${card.line[1]}</b></div>`;
}

function renderStatus(s) {
  state = s;
  renderMarket(s.market);

  const mode = $("modeChip");
  if (s.mode === "signal") { mode.textContent = "Midas"; mode.className = "top-mode"; }
  else if (s.mode === "paper") { mode.textContent = "Paper"; mode.className = "top-mode"; }
  else { mode.textContent = s.risk.armed ? "Armed" : "Live"; mode.className = "top-mode " + (s.risk.armed ? "armed" : "live"); }

  $("heroEquity").classList.remove("skeleton");
  setNumber($("heroEquity"), s.equity, (v) => "$" + money(v));
  $("heroMode").textContent = s.running ? (s.last_error ? "retrying" : "running") : "stopped";

  const daily = s.risk.daily_realized_pnl;
  const startOfDay = s.equity - daily;
  const dailyPct = startOfDay ? (daily / startOfDay) * 100 : 0;
  const change = $("heroChange");
  change.textContent = `${signed(daily)} (${signed(dailyPct)}%) today`;
  tone(change, daily);

  renderRealCheck(s);

  $("stripCash").textContent = `${money(s.balance.available)} ${s.balance.currency}`;
  setNumber($("stripDaily"), daily, (v) => signed(v));
  tone($("stripDaily"), daily);
  $("stripBudget").textContent = money(-s.risk.daily_loss_limit);
  $("stripPositions").textContent = `${s.positions.length} of ${s.risk.max_open_positions ?? "—"}`;
  renderLocks(s.locks || []);

  renderSymbols(s);
  renderPositions(s);
  renderWatchlist(s);
  renderControls(s);
  renderSignals(s);
  renderChartRead();
  renderRun(s.challenge);
}

function renderSymbols(s) {
  const held = new Set(s.positions.map((p) => p.symbol));
  const symbols = s.watchlist.map((r) => r.symbol);
  if (!selected || !symbols.includes(selected)) {
    selected = held.size ? [...held][0] : symbols[0];
    if (selected) loadChart(selected).catch(() => {});
  }
  $("symbolTabs").innerHTML = symbols
    .map((sym) => `<button class="symbol-tab ${sym === selected ? "active" : ""} ${held.has(sym) ? "holding" : ""}" data-symbol="${sym}">${sym}</button>`)
    .join("");

  const row = s.watchlist.find((r) => r.symbol === selected);
  if (row && row.price != null) {
    const el = $("chartQuote");
    el.textContent = money(row.price);
    el.classList.remove("up", "down");
    if (lastQuote !== null && row.price !== lastQuote) el.classList.add(row.price > lastQuote ? "up" : "down");
    lastQuote = row.price;
  }
}

function renderChartRead() {
  const row = (state.watchlist || []).find((r) => r.symbol === selected);
  const host = $("chartRead");
  if (!row || !row.ready) { host.textContent = "Still gathering data."; return; }
  const held = row.position;
  host.textContent =
    `${row.symbol} at ${money(row.price)}, ${pct(row.change_pct)} across this window. `
    + `Trend is ${row.trend}, EMA gap ${pct(row.spread_pct)}, RSI ${money(row.rsi, 0)}. `
    + (held
      ? `Holding ${held.qty} from ${money(held.entry_price)}, ${signed(held.unrealized_pnl)}.`
      : "No position here.");
}

function renderLocks(locks) {
  const host = $("lockRow");
  if (!host) return;
  if (!locks.length) { host.hidden = true; return; }
  host.hidden = false;
  const worst = locks.reduce((a, b) => (b.minutes_left > a.minutes_left ? b : a));
  host.querySelector("b").textContent =
    `${worst.reason}${worst.symbol ? ` · ${worst.symbol}` : ""} · ${worst.minutes_left}m`;
}

function renderPositions(s) {
  $("positionCount").textContent = s.positions.length;
  const host = $("positionList");
  if (!s.positions.length) { host.innerHTML = '<div class="empty">Nothing open.</div>'; return; }
  host.innerHTML = s.positions.map((p) => {
    const c = p.unrealized_pnl >= 0 ? "up" : "down";
    return `<div class="item">
      <span class="ticker">${p.symbol.slice(0, 2)}</span>
      <div class="item-main">
        <div class="item-title">${p.symbol}</div>
        <div class="item-sub">${p.qty} @ ${money(p.entry_price)} → ${money(p.current_price)}</div>
      </div>
      <div class="item-value">
        <b class="${c}">${signed(p.unrealized_pnl)}</b>
        <span class="${c}">${pct(p.unrealized_pnl_pct)}</span>
      </div>
      <button class="small" data-close="${p.symbol}">Close</button>
    </div>`;
  }).join("");
}

function renderWatchlist(s) {
  const rows = s.watchlist;
  $("watchEmpty").style.display = rows.some((r) => r.ready) ? "none" : "block";
  $("watchRows").innerHTML = rows.map((r) => {
    if (!r.ready) {
      return `<div class="item"><span class="ticker">${r.symbol.slice(0, 2)}</span>
        <div class="item-main"><div class="item-title">${r.symbol}</div>
        <div class="item-sub">loading…</div></div></div>`;
    }
    const c = r.change_pct >= 0 ? "up" : "down";
    const pos = r.position ? ` · holding ${r.position.qty}` : "";
    return `<div class="item tappable" data-symbol="${r.symbol}">
      <span class="ticker">${r.symbol.slice(0, 2)}</span>
      <div class="item-main">
        <div class="item-title">${r.symbol}</div>
        <div class="item-sub">${r.trend} · RSI ${money(r.rsi, 0)} · gap ${pct(r.spread_pct)}${pos}</div>
      </div>
      <div class="item-value">
        <b>${money(r.price)}</b>
        <span class="${c}">${pct(r.change_pct)}</span>
      </div>
    </div>`;
  }).join("");
}

function renderControls(s) {
  $("btnStart").disabled = s.running;
  $("btnStop").disabled = !s.running;
  $("btnScan").disabled = !s.running;

  const arm = $("btnArm");
  const hint = $("armHint");

  if (s.mode === "signal") {
    arm.hidden = true;
    hint.className = "note";
    hint.textContent =
      "Midas mode. Midas has no API, so I cannot place orders there — instead I do the "
      + "analysis and hand you the exact trade. I hold no brokerage keys at all, so I "
      + "cannot spend your money even by accident.";
    return;
  }
  arm.hidden = false;
  if (s.mode === "paper") {
    arm.disabled = true;
    hint.className = "note";
    hint.textContent = "Paper mode: real prices, simulated money.";
    return;
  }
  arm.disabled = false;
  arm.textContent = s.risk.armed ? "Disarm" : "Arm live";
  hint.className = s.risk.armed ? "note warn" : "note";
  hint.textContent = s.risk.armed
    ? "Armed — placing real orders with real money."
    : s.risk.disarm_reason ? `Disarmed (${s.risk.disarm_reason}).` : "Disarmed. No real orders until you arm.";
}

function renderSignals(s) {
  const tray = $("signalTray");
  const pending = s.pending_signals || [];
  if (!pending.length) { tray.innerHTML = ""; return; }

  tray.innerHTML = pending.map((sig) => {
    const exit = sig.kind === "exit";
    const rows = exit
      ? `<div class="row"><span>Sell</span><b>${sig.qty} shares</b></div>
         <div class="row"><span>Around</span><b>${money(sig.price)}</b></div>`
      : `<div class="row"><span>Buy</span><b>${sig.qty} shares</b></div>
         <div class="row"><span>Entry</span><b>${money(sig.price)}</b></div>
         <div class="row"><span>Stop</span><b class="down">${money(sig.stop_loss)}</b></div>
         <div class="row"><span>Target</span><b class="up">${money(sig.take_profit)}</b></div>
         <div class="row"><span>At risk</span><b>$${money(sig.risk_amount)}</b></div>`;
    return `<div class="signal">
      <div class="signal-top">
        <span class="signal-title">${exit ? "Sell" : "Buy"} ${sig.symbol}</span>
        <span class="signal-tag">place in Midas</span>
      </div>
      <div class="signal-why">${sig.reason}</div>
      <div class="rows signal-rows">${rows}</div>
      <div class="signal-actions">
        <input type="number" step="0.01" placeholder="fill" data-fill="${sig.id}">
        <button class="solid" data-taken="${sig.id}">Taken</button>
        <button data-skipped="${sig.id}">Skipped</button>
      </div>
    </div>`;
  }).join("");
}

function renderTrades(payload) {
  const st = payload.stats;
  setNumber($("statTrades"), st.total_trades, (v) => String(Math.round(v)));
  $("statWinRate").textContent = st.total_trades ? `${st.win_rate}%` : "—";
  $("statFactor").textContent = st.profit_factor || "—";
  setNumber($("statPnl"), st.total_pnl, (v) => signed(v));
  tone($("statPnl"), st.total_pnl);

  const rows = payload.trades;
  $("historyCount").textContent = rows.length;
  $("tradesEmpty").style.display = rows.length ? "none" : "block";
  $("tradeRows").innerHTML = rows.map((tr) => {
    const c = tr.pnl >= 0 ? "up" : "down";
    return `<div class="item">
      <div class="item-main">
        <div class="item-title">${tr.symbol}</div>
        <div class="item-sub">${stamp(tr.closed_at)} · ${tr.exit_reason}</div>
      </div>
      <div class="item-value">
        <b class="${c}">${signed(tr.pnl)}</b>
        <span class="${c}">${pct(tr.pnl_pct)}</span>
      </div>
    </div>`;
  }).join("");
}

function renderSetup(data) {
  const done = data.checks.filter((c) => c.done).length;
  $("setupProgress").textContent = `${done}/${data.checks.length}`;

  $("setupSteps").innerHTML = data.checks.map((c, i) => {
    const code = c.code
      ? `<div class="code"><button class="small" data-copy="${encodeURIComponent(c.code)}">Copy</button>${c.code}</div>` : "";
    const link = c.action ? `<a class="step-link" href="${c.action}" target="_blank" rel="noopener">${c.action_label} ↗</a>` : "";
    const detail = c.detail ? `<div class="step-detail">${c.detail}</div>` : "";
    return `<li class="step ${c.done ? "done" : ""}">
      <div class="step-num">${c.done ? "✓" : i + 1}</div>
      <div class="step-body">
        <div class="step-title">${c.title}</div>
        <div class="step-text">${c.body}</div>
        ${detail}${code}${link}
      </div>
    </li>`;
  }).join("");

  const r = data.risk;
  $("railGrid").innerHTML = [
    ["Position size", `${r.max_position_pct}% of equity`],
    ["Stop-loss", `-${r.stop_loss_pct}% every trade`],
    ["Take-profit", `+${r.take_profit_pct}% every trade`],
    ["Daily loss limit", `-${r.max_daily_loss_pct}%, then disarms`],
    ["Max positions", `${r.max_open_positions} at once`],
  ].map(([k, v]) => `<div class="row"><span>${k}</span><b class="plain">${v}</b></div>`).join("");

  const c = data.integrations;
  $("connGrid").innerHTML = [
    ["Broker", c.alpaca], ["Telegram", c.telegram],
    ["Claude", c.claude], ["Dashboard token", c.dashboard_token],
  ].map(([k, on]) => `<div class="row"><span>${k}</span><b class="plain">${on ? "connected" : "not set"}</b></div>`).join("");
}

/* ==================================================================== data */

async function get(path) {
  const res = await fetch(q(path));
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function send(method, path, body) {
  const res = await fetch(q(path), {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body || {}),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    // FastAPI validation errors arrive as a list of field problems.
    const message = Array.isArray(detail.detail)
      ? detail.detail.map((d) => d.msg || "").join("; ")
      : detail.detail;
    throw new Error(message || res.statusText);
  }
  return res.json();
}

const post = (path, body) => send("POST", path, body || {});
const patch = (path, body) => send("PATCH", path, body || {});
const del = (path) => send("DELETE", path);

async function loadChart(symbol) {
  if (!symbol) return;
  const { candles, overlays } = await get(`/api/candles/${symbol}`);
  if (!candles.length) { $("chartNote").textContent = `No candles for ${symbol} yet.`; return; }
  candleSeries.setData(candles);
  $("chartNote").textContent = `${symbol} · ${candles.length} bars`;

  const wanted = new Set(Object.keys(overlays));
  overlaySeries.forEach((series, name) => {
    if (!wanted.has(name)) { chart.removeSeries(series); overlaySeries.delete(name); }
  });
  Object.entries(overlays).forEach(([name, points], i) => {
    let series = overlaySeries.get(name);
    if (!series) {
      series = chart.addLineSeries({
        color: overlayColors[i % overlayColors.length],
        lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      });
      overlaySeries.set(name, series);
    }
    series.setData(points);
  });
  drawPositionLines((state.positions || []).find((p) => p.symbol === symbol));
}

async function loadEquity() {
  const { curve } = await get("/api/equity");
  // Needs enough points AND some actual movement — a dead-flat line renders as a
  // stray bar rather than a chart, so collapse the panel until equity has moved.
  const values = curve.map((p) => p.value);
  const moved = values.length >= 5 && Math.max(...values) > Math.min(...values);
  $("equitySpark").style.display = moved ? "" : "none";
  if (moved) sparkSeries.setData(curve);
}

async function loadSetup() { renderSetup(await get("/api/setup")); }

async function loadRun() {
  runConfig = await get("/api/challenge");
  renderRun(runConfig.active);
}

async function refresh() {
  const [status, trades] = await Promise.all([get("/api/status"), get("/api/trades")]);
  renderStatus(status);
  renderTrades(trades);
}

/* =============================================================== websocket */

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}${q("/api/ws")}`);

  socket.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "status") renderStatus(msg);
    else if (msg.type === "mentor") pushLine(msg.line);
    else if (msg.type === "challenge") loadRun().catch(() => {});
    else if (msg.type === "trade_closed") {
      get("/api/trades").then(renderTrades).catch(() => {});
      loadEquity().catch(() => {});
      alertTradeClosed(msg);
    } else if (msg.type === "trade_opened" || msg.type === "signal_raised") {
      if (selected) loadChart(selected).catch(() => {});
      if (msg.type === "trade_opened") alertTradeOpened(msg);
    } else if (msg.type === "catalyst" && msg.event === "window_open") {
      alertCatalyst(msg.catalyst);
    }
  };
  socket.onclose = () => setTimeout(connect, 3000);
}

/* =================================================================== news */

async function loadNews() {
  const host = $("newsFeed");
  if (!host) return;
  host.innerHTML = '<div class="empty">Loading…</div>';

  try {
    const data = await get("/api/news");
    $("newsScope").textContent = data.symbols.length
      ? `Watching ${data.symbols.length} symbols: ${data.symbols.join(", ")}`
      : "";

    if (!data.available) {
      host.innerHTML =
        '<div class="empty">The news feed needs broker keys in .env. '
        + "Everything else still works.</div>";
      return;
    }
    if (!data.news.length) {
      host.innerHTML = '<div class="empty">No recent headlines for what you are watching.</div>';
      return;
    }

    host.innerHTML = data.news.map((n) => `
      <article class="news-item">
        <div class="news-head">${escapeHtml(n.headline || "")}</div>
        <div class="news-meta">${escapeHtml(stamp(n.created_at))} · ${escapeHtml(n.source || "")}</div>
        ${(n.symbols || []).length
          ? `<div class="news-syms">${n.symbols.map((s) =>
              `<span>${escapeHtml(s)}</span>`).join("")}</div>`
          : ""}
      </article>`).join("");
    $("newsDot").hidden = true;
  } catch (err) {
    host.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}

/* ================================================================= alerts */

/* A banner is an interruption, so it is spent only on things that changed the
   money or the plan. Everything quieter belongs in the chat rail. */

const ALERT_LIFE = 9000;

function showAlert({ tone = "info", title, body, symbol }) {
  const host = $("alertStack");
  if (!host) return;

  const card = document.createElement("div");
  card.className = `alert ${tone}`;
  card.innerHTML = `
    ${symbol ? `<span class="ticker">${escapeHtml(symbol.slice(0, 2))}</span>` : ""}
    <div class="alert-main">
      <b>${escapeHtml(title)}</b>
      ${body ? `<span>${escapeHtml(body)}</span>` : ""}
    </div>
    <button class="icon" aria-label="Dismiss">
      <svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>
    </button>`;

  const close = () => {
    card.classList.add("leaving");
    // Let the exit animation finish before the node goes, or it vanishes.
    setTimeout(() => card.remove(), 320);
  };
  card.querySelector("button").onclick = close;
  setTimeout(close, ALERT_LIFE);

  host.prepend(card);
  // Three is enough to notice; more is a log, and we already have one.
  while (host.children.length > 3) host.lastElementChild.remove();
}

function alertTradeOpened(msg) {
  const p = msg.position || {};
  showAlert({
    tone: "info",
    symbol: p.symbol,
    title: `Bought ${p.qty} ${p.symbol}`,
    body: [
      p.entry_price ? `at ${money(p.entry_price)}` : null,
      p.stop_loss ? `stop ${money(p.stop_loss)}` : null,
      p.take_profit ? `target ${money(p.take_profit)}` : null,
    ].filter(Boolean).join(" · "),
  });
}

function alertTradeClosed(msg) {
  const won = (msg.pnl ?? 0) >= 0;
  showAlert({
    tone: won ? "good" : "bad",
    symbol: msg.symbol,
    title: `Closed ${msg.symbol} ${signed(msg.pnl)} (${signed(msg.pnl_pct)}%)`,
    body: msg.exit_reason ? `Exit: ${msg.exit_reason}` : null,
  });
}

function alertCatalyst(catalyst) {
  if (!catalyst) return;
  showAlert({
    tone: "info",
    symbol: catalyst.symbol,
    title: `Entry window open — ${catalyst.symbol}`,
    body: `${catalyst.title} · ${catalyst.days_away} days away`,
  });
}

/* ================================================================ actions */

async function act(fn) {
  try {
    const r = await fn();
    if (r && r.mode) renderStatus(r);
  } catch (err) {
    addMessage({ text: err.message, level: "warn" });
  }
}

const newsRefresh = $("newsRefresh");
if (newsRefresh) newsRefresh.onclick = () => loadNews().catch(() => {});

$("btnStart").onclick = () => act(() => post("/api/engine/start"));
$("btnStop").onclick = () => act(() => post("/api/engine/stop"));
$("btnScan").onclick = () => act(() => post("/api/engine/scan"));

$("btnArm").onclick = () => {
  if (state.risk && state.risk.armed) return act(() => post("/api/disarm"));
  if (confirm("Arm live trading?\n\nThe bot will place real orders with real money.\nIt disarms on the daily loss limit and on every restart."))
    act(() => post("/api/arm", { confirm: true }));
};

$("addForm").onsubmit = (e) => {
  e.preventDefault();
  const symbol = $("addSymbol").value.trim().toUpperCase();
  if (!symbol) return;
  $("addSymbol").value = "";
  act(() => post("/api/watchlist/add", { symbol }));
};

/* "remember that ..." is handled here rather than by the model, so a fact is
   stored exactly as typed instead of depending on the model to call a tool. */
const REMEMBER = /^(remember|hatirla|hatırla)\b[:,]?\s*(that\s+)?/i;

$("askForm").onsubmit = async (e) => {
  e.preventDefault();
  const question = $("askInput").value.trim();
  if (!question) return;
  $("askInput").value = "";
  addMessage({ text: question, from: "you" });
  $("askButton").disabled = true;

  const asFact = question.replace(REMEMBER, "");
  if (REMEMBER.test(question) && asFact) {
    try {
      const { memory } = await post("/api/mentor/memory", { text: asFact });
      aiMemory = memory;
      renderMemory();
      addMessage({ text: `Noted. I will keep that in mind from now on.`, level: "result" });
    } catch (err) {
      addMessage({ text: err.message, level: "warn" });
    } finally { $("askButton").disabled = false; }
    return;
  }

  showTyping(true);
  try {
    const { answer } = await post("/api/ask", { question });
    showTyping(false);
    addMessage({ text: answer, level: "answer" });
  } catch (err) {
    showTyping(false);
    addMessage({ text: claudeReady ? err.message : NO_AI_HELP, level: "warn" });
  } finally { $("askButton").disabled = false; }
};

$("memoryList").onclick = async (e) => {
  const btn = e.target.closest("[data-forget]");
  if (!btn) return;
  try {
    const { memory } = await del(`/api/mentor/memory/${btn.dataset.forget}`);
    aiMemory = memory;
    renderMemory();
  } catch (err) { addMessage({ text: err.message, level: "warn" }); }
};

$("symbolTabs").onclick = (e) => {
  const tab = e.target.closest(".symbol-tab");
  if (!tab) return;
  selected = tab.dataset.symbol;
  renderSymbols(state);
  renderChartRead();
  loadChart(selected).catch(() => {});
};

document.addEventListener("click", async (e) => {
  const stakeBtn = e.target.closest("[data-stake]");
  if (stakeBtn) { pickStake = Number(stakeBtn.dataset.stake); paintPicker(); return; }

  const multBtn = e.target.closest("[data-mult]");
  if (multBtn) { pickMult = Number(multBtn.dataset.mult); paintPicker(); return; }

  if (e.target.closest("#btnRunStart")) {
    const target = pickStake * pickMult;
    if (!confirm(`Start a run with ${cur()}${money(pickStake)}, aiming for ${cur()}${money(target)}?\n\nPaper money.`)) return;
    try {
      renderStatus(await post("/api/challenge/start", { stake: pickStake, target }));
      await loadRun();
      openAI(true);
    } catch (err) { alert(err.message); }
    return;
  }

  if (e.target.closest("#btnRunStop")) {
    if (!confirm("End this run?")) return;
    try { renderStatus(await post("/api/challenge/stop")); await loadRun(); }
    catch (err) { alert(err.message); }
    return;
  }

  const copy = e.target.closest("[data-copy]");
  if (copy) {
    navigator.clipboard.writeText(decodeURIComponent(copy.dataset.copy));
    copy.textContent = "Copied";
    setTimeout(() => (copy.textContent = "Copy"), 1600);
    return;
  }

  const close = e.target.closest("[data-close]");
  if (close) {
    e.stopPropagation();
    if (confirm(`Close ${close.dataset.close} at the current price?`))
      act(() => post(`/api/close/${close.dataset.close}`));
    return;
  }

  const taken = e.target.closest("[data-taken]");
  if (taken) {
    const id = taken.dataset.taken;
    const input = document.querySelector(`[data-fill="${id}"]`);
    const price = input && input.value ? parseFloat(input.value) : null;
    act(() => post(`/api/signals/${id}/taken`, { price }));
    return;
  }

  const skipped = e.target.closest("[data-skipped]");
  if (skipped) { act(() => post(`/api/signals/${skipped.dataset.skipped}/skipped`)); return; }

  const catStatus = e.target.closest("[data-cat-status]");
  if (catStatus) {
    try {
      await patch(`/api/catalysts/${catStatus.dataset.catStatus}`, { status: catStatus.dataset.to });
      await loadCatalysts();
    } catch (err) { alert(err.message); }
    return;
  }

  const catDel = e.target.closest("[data-cat-del]");
  if (catDel) {
    if (!confirm("Remove this catalyst?")) return;
    try {
      await del(`/api/catalysts/${catDel.dataset.catDel}`);
      await loadCatalysts();
    } catch (err) { alert(err.message); }
    return;
  }

  const goto = e.target.closest("[data-goto]");
  if (goto) { showView(goto.dataset.goto); return; }

  const row = e.target.closest("[data-symbol]");
  if (row && row.classList.contains("tappable")) {
    selected = row.dataset.symbol;
    renderSymbols(state);
    renderChartRead();
    showView("chart");
  }
});

/* =================================================================== boot */

(async () => {
  const step = (text) => { const el = $("bootStep"); if (el) el.textContent = text; };
  // The mark's grow animation runs about a second; holding the splash for at
  // least that long stops it flashing past on a warm start.
  const shown = new Promise((done) => setTimeout(done, 1150));

  try {
    step("reading your account…");
    await loadRun();
    await refresh();

    step("waking the mentor…");
    const mentor = await get("/api/mentor");
    const ai = mentor.ai || {};
    claudeReady = mentor.claude;
    aiMemory = mentor.memory || [];
    renderMemory();

    // Name the model that is actually answering, rather than a vague "connected".
    $("aiState").textContent = claudeReady
      ? `${ai.model || ai.provider}${ai.free ? " · free" : ""}`
      : "narrating only · no AI connected";
    $("askInput").placeholder = claudeReady
      ? "Ask anything, or say \"remember …\""
      : "No AI connected — see .env";

    mentor.lines.forEach(pushLine);
    scrollChat(true);

    step("drawing the curve…");
    await loadEquity();
    step("ready");
  } catch (err) {
    console.error(err);
    step("could not reach the bot — retrying");
  }

  await shown;
  $("boot").classList.add("gone");

  connect();
  setInterval(() => refresh().catch(() => {}), 20000);
})();
