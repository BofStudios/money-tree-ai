/* The research surface: search a company, choose how deep to go, read the data.
 *
 * Two ideas run through the whole file.
 *
 * Simple vs Advanced is one dataset rendered two ways. The plain-language
 * sentence and the raw indicator value come from the same payload, so the two
 * modes can never drift apart or disagree.
 *
 * A missing number renders as "—" carrying a tooltip that says the provider
 * doesn't supply it. It never renders as 0, and never as a plausible guess.
 */

import { t, setLanguage, getLanguage, applyTranslations, LANGUAGES } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const TOKEN = new URLSearchParams(location.search).get("token") || "";
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);

let symbol = null;
let payload = null;
let depth = "standard";
let attention = [];
let mode = "simple";
let profile = null;

/* ------------------------------------------------------------------ fetch */

async function api(method, path, body) {
  const res = await fetch(q(path), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map((d) => d.msg).join(", ")
        : t("error.data")
    );
  }
  return data;
}
const get = (p) => api("GET", p);
const post = (p, b) => api("POST", p, b);
const patch = (p, b) => api("PATCH", p, b);

/* --------------------------------------------------------------- formatting */

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** A missing figure, marked as missing rather than dressed up as a zero. */
const missing = () => `<span class="na" title="${esc(t("naHint"))}">—</span>`;

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

function money(v, digits = 2) {
  if (!isNum(v)) return missing();
  const abs = Math.abs(v);
  // Market caps and revenues are unreadable in full, so scale the big ones.
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  return v.toLocaleString(getLanguage() === "tr" ? "tr-TR" : "en-US", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

function pct(v, digits = 1) {
  if (!isNum(v)) return missing();
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}

function ratio(v, digits = 2) {
  return isNum(v) ? v.toFixed(digits) : missing();
}

function toneOf(v) {
  return isNum(v) ? (v > 0 ? "up" : v < 0 ? "down" : "") : "";
}

function ago(iso) {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 90) return t("market.updated", { ago: `${Math.round(seconds)}s` });
  if (seconds < 5400) return t("market.updated", { ago: `${Math.round(seconds / 60)}m` });
  return t("market.updated", { ago: `${Math.round(seconds / 3600)}h` });
}

/* ------------------------------------------------------------------ search */

let searchTimer = null;

function wireSearch() {
  const input = $("rSearch");
  input.addEventListener("input", () => {
    const value = input.value.trim();
    $("rClear").hidden = !value;
    clearTimeout(searchTimer);
    if (value.length < 2) { $("rResults").hidden = true; return; }
    // Debounced: every keystroke would be a provider round trip otherwise.
    searchTimer = setTimeout(() => runSearch(value), 280);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(searchTimer);
      const first = $("rResults").querySelector("[data-symbol]");
      if (first) open(first.dataset.symbol);
      else if (input.value.trim()) open(input.value.trim().toUpperCase());
    }
    if (e.key === "Escape") { $("rResults").hidden = true; input.blur(); }
  });

  $("rClear").onclick = () => {
    input.value = "";
    $("rClear").hidden = true;
    $("rResults").hidden = true;
    input.focus();
  };

  $("rResults").onclick = (e) => {
    const row = e.target.closest("[data-symbol]");
    if (row) open(row.dataset.symbol);
  };
}

async function runSearch(query) {
  try {
    const { results } = await get(`/api/research/search?q=${encodeURIComponent(query)}`);
    const host = $("rResults");
    if (!results.length) {
      host.innerHTML = `<div class="finder-empty">${esc(t("error.notFound"))}</div>`;
    } else {
      host.innerHTML = results.map((r) => `
        <button class="finder-row" data-symbol="${esc(r.symbol)}">
          <span class="ticker">${esc(r.symbol.slice(0, 2))}</span>
          <span class="finder-main">
            <b>${esc(r.symbol)}</b>
            <small>${esc(r.name || "")}</small>
          </span>
          <small class="finder-ex">${esc(r.exchange || "")}</small>
        </button>`).join("");
    }
    host.hidden = false;
  } catch (err) {
    $("rResults").innerHTML = `<div class="finder-empty">${esc(err.message)}</div>`;
    $("rResults").hidden = false;
  }
}

/* ------------------------------------------------------------------- open */

async function open(sym) {
  symbol = String(sym).toUpperCase();
  $("rResults").hidden = true;
  $("rSearch").value = symbol;
  $("rClear").hidden = false;
  $("rEmpty").hidden = true;
  $("rCompany").hidden = false;
  $("rNote").hidden = true;
  $("rAnalysisError").hidden = true;

  $("rName").textContent = symbol;
  $("rMeta").textContent = t("loading.data");
  $("rPrice").classList.add("skeleton");

  try {
    payload = await get(`/api/research/${encodeURIComponent(symbol)}?depth=${depth}`);
  } catch (err) {
    $("rCompany").hidden = true;
    $("rEmpty").hidden = false;
    $("rEmpty").innerHTML = `<h3>${esc(t("error.data"))}</h3><p>${esc(err.message)}</p>`;
    return;
  }
  render();
}

/* ----------------------------------------------------------------- render */

function render() {
  if (!payload) return;
  const p = payload.profile || {};
  const price = payload.price || {};

  $("rTicker").textContent = symbol.slice(0, 2);
  $("rName").textContent = p.name || symbol;
  $("rMeta").textContent = [p.sector, p.industry, p.exchange].filter(Boolean).join(" · ") || symbol;

  $("rPrice").classList.remove("skeleton");
  $("rPrice").innerHTML = isNum(price.price) ? money(price.price) : missing();
  const change = $("rChange");
  change.innerHTML = isNum(price.change)
    ? `${money(price.change)} (${pct(price.change_pct, 2)})`
    : missing();
  change.className = "hero-change " + toneOf(price.change);

  const stamp = price.provenance && price.provenance.as_of;
  $("rFresh").textContent = [ago(stamp), t("market.delayed")].filter(Boolean).join(" · ");

  renderDepth();
  renderAttention();
  renderPlan();
  renderSections();
  applyTranslations($("rCompany"));
}

function renderDepth() {
  const options = ["quick", "standard", "deep", "full"];
  $("rDepth").innerHTML = options.map((key) => `
    <button class="depth ${key === depth ? "active" : ""}" data-depth="${key}">
      <b>${esc(t(`research.depth.${key}`))}</b>
      <small>${esc(t(`research.depth.${key}What`))}</small>
    </button>`).join("");
}

const ATTENTION = [
  "growth", "profitability", "valuation", "debt", "cash_flow",
  "dividends", "momentum", "news", "risks", "earnings", "ownership",
];

function renderAttention() {
  $("rAttention").innerHTML = ATTENTION.map((key) => `
    <button class="chip pickable ${attention.includes(key) ? "on" : ""}" data-attention="${key}">
      ${esc(t(`a.${key}`))}
    </button>`).join("")
    + `<button class="chip pickable ${attention.length === 0 ? "on" : ""}" data-attention="__none">
         ${esc(t("a.unknown"))}
       </button>`;
}

/* The server names plan steps in English because that is the language the model
   is prompted in. The screen is the reader's, so translate by key here and keep
   the server label only as the fallback for a step we have no string for. */
const STEP_KEYS = {
  profile: "section.overview", price: "section.price", technicals: "section.technicals",
  quality: "section.quality", valuation: "section.valuation", earnings: "section.earnings",
  analysts: "section.analysts", statements: "section.statements",
  dividend: "section.dividend", ownership: "section.ownership", news: "section.news",
};

const stepLabel = (step) => (STEP_KEYS[step.key] ? t(STEP_KEYS[step.key]) : step.label);

function renderPlan() {
  const plan = payload.plan;
  const host = $("rPlan");
  if (!plan || !plan.steps.length) { host.hidden = true; return; }

  const steps = plan.steps.map((s, i) => `
    <li class="${s.focused ? "focused" : ""}">
      <i>${String(i + 1).padStart(2, "0")}</i>${esc(stepLabel(s))}
    </li>`).join("");

  const skipped = plan.skipped.length
    ? `<p class="note faint">${esc(t("research.planSkipped"))}: ${
        plan.skipped.map((s) => esc(stepLabel(s))).join(", ")}</p>`
    : "";

  host.innerHTML = `<h3>${esc(t("research.plan"))}</h3><ol class="plan-steps">${steps}</ol>${skipped}`;
  host.hidden = false;
}

/* --------------------------------------------------------------- sections */

/** One metric row. `plain` is what Simple mode shows instead of the number. */
function metric(labelKey, value, opts = {}) {
  const { explain, plain, tone } = opts;
  const shown = mode === "simple" && plain ? esc(plain) : value;
  return `
    <div class="row metric">
      <span>
        ${esc(t(labelKey))}
        ${explain ? `<button class="why" data-explain="${esc(explain)}"
                       data-term="${esc(t(labelKey))}">${esc(t("action.why"))}</button>` : ""}
      </span>
      <b class="${tone || ""}">${shown}</b>
    </div>`;
}

function block(titleKey, inner, note) {
  if (!inner) return "";
  return `
    <section class="block">
      <div class="block-head"><h2>${esc(t(titleKey))}</h2>
        ${note ? `<span class="muted">${esc(note)}</span>` : ""}</div>
      ${inner}
    </section>`;
}

function renderSections() {
  const parts = [];
  const { profile: p, price, valuation: v, quality: qu, technicals, earnings,
          analysts, dividend, ownership, statements, news } = payload;

  /* --- business ------------------------------------------------------- */
  if (p && p.summary) {
    parts.push(block("section.overview", `
      <p class="prose">${esc(p.summary.slice(0, 700))}${p.summary.length > 700 ? "…" : ""}</p>
      <div class="rows">
        ${metric("metric.marketCap", money(price && price.market_cap))}
        ${metric("metric.beta", ratio(price && price.beta), {
          explain: "Beta compares how much this moves against the wider market. "
            + "1.0 means it typically moves in line with the index; above that, it "
            + "swings harder in both directions.",
        })}
      </div>`));
  }

  /* --- price ---------------------------------------------------------- */
  if (price) {
    const range = isNum(price.week52_low) && isNum(price.week52_high)
      ? `${money(price.week52_low)} – ${money(price.week52_high)}` : missing();
    parts.push(block("section.price", `
      <div class="rows">
        ${metric("metric.week52", range)}
        ${metric("metric.fromHigh", pct(price.from_52w_high_pct), { tone: toneOf(price.from_52w_high_pct) })}
        ${metric("metric.fromLow", pct(price.from_52w_low_pct), { tone: toneOf(price.from_52w_low_pct) })}
        ${metric("metric.relVolume", ratio(price.relative_volume), {
          plain: isNum(price.relative_volume)
            ? (price.relative_volume >= 1.25 ? t("state.increasing")
              : price.relative_volume <= 0.75 ? t("state.declining") : t("state.normal"))
            : null,
          explain: "How today's trading volume compares with its recent average. "
            + "Above 1 means more people are trading it than usual.",
        })}
      </div>`));
  }

  /* --- technicals ----------------------------------------------------- */
  if (technicals) {
    const badges = [
      ["state." + (technicals.trend || ""), technicals.trend],
      ["state." + (technicals.momentum || ""), technicals.momentum],
      ["state." + (technicals.volatility || ""), technicals.volatility],
    ].filter(([, v]) => v)
     .map(([key]) => `<span class="badge">${esc(t(key))}</span>`).join("");

    const levels = (technicals.support || []).length || (technicals.resistance || []).length
      ? `<div class="levels">
           <div><span>${esc(t("state.support"))}</span><b>${
             (technicals.support || []).map((n) => money(n)).join(" · ") || missing()}</b></div>
           <div><span>${esc(t("state.resistance"))}</span><b>${
             (technicals.resistance || []).map((n) => money(n)).join(" · ") || missing()}</b></div>
         </div>` : "";

    // Simple mode reads the sentences; Advanced adds the raw values beside them.
    const readings = (technicals.readings || []).map((r) => `
      <div class="reading">
        <div class="reading-top">
          <span class="reading-label">${esc(r.label)}</span>
          ${mode === "advanced"
            ? `<b class="reading-value">${isNum(r.value) ? r.value : missing()}</b>` : ""}
          ${r.state ? `<span class="pill sm">${esc(r.state)}</span>` : ""}
        </div>
        <p>${esc(r.plain || "")}</p>
        ${r.explain ? `<button class="why" data-explain="${esc(r.explain)}"
                        data-term="${esc(r.label)}">${esc(t("action.why"))}</button>` : ""}
      </div>`).join("");

    parts.push(block("section.technicals",
      `<p class="prose">${esc(technicals.summary || "")}</p>
       <div class="badges">${badges}</div>${levels}
       <div class="readings">${readings}</div>`,
      `${technicals.bars} bars`));
  }

  /* --- financial health ----------------------------------------------- */
  if (qu) {
    parts.push(block("section.quality", `
      <div class="rows">
        ${metric("metric.revenue", money(qu.revenue))}
        ${metric("metric.revenueGrowth", pct(qu.revenue_growth_pct), {
          tone: toneOf(qu.revenue_growth_pct),
          explain: "How much bigger the company's sales are than a year ago.",
        })}
        ${metric("metric.netMargin", pct(qu.net_margin_pct), {
          explain: "Of every 100 in sales, how much is left as profit after all costs.",
        })}
        ${metric("metric.operatingMargin", pct(qu.operating_margin_pct))}
        ${metric("metric.grossMargin", pct(qu.gross_margin_pct))}
        ${metric("metric.roe", pct(qu.return_on_equity_pct), {
          explain: "Return on equity: the profit made for every unit of shareholder "
            + "money invested. Higher is generally better, but heavy borrowing can "
            + "flatter it.",
        })}
        ${metric("metric.fcf", money(qu.free_cash_flow), {
          explain: "Free cash flow is the cash left after running the business and "
            + "paying for equipment. It is harder to massage than reported profit.",
        })}
        ${metric("metric.cash", money(qu.total_cash))}
        ${metric("metric.debt", money(qu.total_debt))}
        ${metric("metric.netDebt", money(qu.net_debt), {
          explain: "Total debt minus cash on hand. Negative means the company holds "
            + "more cash than it owes.",
        })}
        ${metric("metric.debtEquity", ratio(qu.debt_to_equity, 1), {
          explain: "Debt measured against shareholder equity, as a percentage. "
            + "Higher means more of the business is funded by borrowing.",
        })}
        ${metric("metric.currentRatio", ratio(qu.current_ratio))}
      </div>`));
  }

  /* --- valuation ------------------------------------------------------ */
  if (v) {
    parts.push(block("section.valuation", `
      <div class="rows">
        ${metric("metric.pe", ratio(v.pe), {
          explain: "Price-to-earnings: how many years of current profit you are "
            + "paying for one share. A high number means the market expects growth — "
            + "and will be disappointed if it doesn't arrive.",
        })}
        ${metric("metric.forwardPe", ratio(v.forward_pe))}
        ${metric("metric.peg", ratio(v.peg), {
          explain: "P/E divided by the growth rate. Around 1 is often called fair, "
            + "but it depends entirely on the growth estimate being right.",
        })}
        ${metric("metric.ps", ratio(v.price_to_sales))}
        ${metric("metric.pb", ratio(v.price_to_book))}
        ${metric("metric.evEbitda", ratio(v.ev_to_ebitda), {
          explain: "Enterprise value against operating earnings. It includes debt, "
            + "so it compares companies with different borrowing more fairly than P/E.",
        })}
        ${metric("metric.fcfYield", pct(v.fcf_yield_pct), {
          explain: "Free cash flow as a percentage of the company's market value — "
            + "roughly the cash return if you owned the whole business.",
        })}
        ${metric("metric.eps", ratio(v.eps))}
        ${metric("metric.dividendYield", pct(v.dividend_yield_pct, 2))}
      </div>`));
  }

  /* --- earnings ------------------------------------------------------- */
  if (earnings) {
    const rows = (earnings.history || []).slice(0, 6).map((e) => `
      <div class="row metric">
        <span>${esc(e.date || "")}</span>
        <b class="${toneOf(e.surprise_pct)}">${
          isNum(e.eps_actual) ? `${e.eps_actual} vs ${isNum(e.eps_estimate) ? e.eps_estimate : "—"}` : missing()
        } ${isNum(e.surprise_pct) ? `(${pct(e.surprise_pct)})` : ""}</b>
      </div>`).join("");
    const record = isNum(earnings.beats) || isNum(earnings.misses)
      ? `${earnings.beats || 0} beats · ${earnings.misses || 0} misses` : "";
    parts.push(block("section.earnings",
      `<div class="rows">
         ${metric("metric.nextEarnings", earnings.next_date ? esc(earnings.next_date) : missing())}
         ${rows}
       </div>`, record));
  }

  /* --- analysts ------------------------------------------------------- */
  if (analysts) {
    const spread = ["strong_buy", "buy", "hold", "sell", "strong_sell"]
      .filter((k) => isNum(analysts[k]) && analysts[k] > 0)
      .map((k) => `<span class="pill sm">${k.replace("_", " ")} ${analysts[k]}</span>`).join("");
    parts.push(block("section.analysts", `
      <div class="rows">
        ${metric("metric.consensus", analysts.consensus ? esc(analysts.consensus) : missing())}
        ${metric("metric.analysts", isNum(analysts.analyst_count) ? analysts.analyst_count : missing())}
        ${metric("metric.targetMean", money(analysts.target_mean))}
      </div>
      ${spread ? `<div class="badges">${spread}</div>` : ""}
      <p class="note faint">Published targets are other people's opinions, not a
      measurement. They are shown because they move prices, not because they are right.</p>`));
  }

  /* --- statements ----------------------------------------------------- */
  if (statements && (statements.annual || []).length) {
    const lines = statements.annual;
    const periods = lines[0].periods || [];
    const head = periods.map((p) => `<th>${esc((p || "").slice(0, 7))}</th>`).join("");
    const body = lines.map((l) => `
      <tr><th>${esc(l.label)}</th>${
        l.values.map((val) => `<td>${money(val)}</td>`).join("")}</tr>`).join("");
    parts.push(block("section.statements",
      `<div class="table-wrap"><table class="fin">
         <thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table></div>`));
  }

  /* --- dividend ------------------------------------------------------- */
  if (dividend) {
    parts.push(block("section.dividend", `
      <div class="rows">
        ${metric("metric.dividendYield", pct(dividend.yield_pct, 2))}
        ${metric("metric.payout", pct(dividend.payout_ratio_pct), {
          explain: "The share of profit paid out as dividends. Above 100% means the "
            + "company is paying out more than it earned, which cannot continue forever.",
        })}
        ${metric("metric.exDate", dividend.ex_date ? esc(dividend.ex_date) : missing())}
      </div>`));
  }

  /* --- ownership ------------------------------------------------------ */
  if (ownership) {
    const holders = (ownership.top_holders || []).slice(0, 5).map((h) => `
      <div class="row metric"><span>${esc(h.name || "")}</span>
        <b>${pct(h.pct_held, 2)}</b></div>`).join("");
    parts.push(block("section.ownership",
      `<div class="rows">
         ${metric("metric.consensus", pct(ownership.institution_pct))}
         ${holders}
       </div>`));
  }

  /* --- news ----------------------------------------------------------- */
  if (news && news.length) {
    const items = news.slice(0, 8).map((n) => `
      <article class="news-item">
        <div class="news-head">${esc(n.headline || "")}</div>
        <div class="news-meta">${esc((n.created_at || "").slice(0, 10))} · ${esc(n.source || "")}</div>
      </article>`).join("");
    parts.push(block("section.news", items));
  } else {
    parts.push(block("section.news", `<p class="note faint">${esc(t("empty.news"))}</p>`));
  }

  $("rSections").innerHTML = parts.join("");
}

/* --------------------------------------------------------------- analysis */

async function runAnalysis() {
  const button = $("rRun");
  button.disabled = true;
  button.textContent = t("research.running") + "…";
  $("rAnalysisError").hidden = true;
  $("rNote").hidden = true;

  try {
    const { note, plan } = await post(`/api/research/${encodeURIComponent(symbol)}/analyse`, {
      depth, attention,
    });
    payload.plan = plan;
    renderPlan();
    $("rNote").innerHTML = markdown(note);
    $("rNote").hidden = false;
    button.textContent = t("research.again");
  } catch (err) {
    $("rAnalysisError").textContent = err.message;
    $("rAnalysisError").hidden = false;
    button.textContent = t("research.start");
  } finally {
    button.disabled = false;
  }
}

/** Just enough Markdown for the shapes the analyst is asked to produce. */
function markdown(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let inList = false;

  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    if (inList) { out.push("</ul>"); inList = false; }

    if (!line.trim()) continue;
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) { out.push(`<h4>${inline(heading[1])}</h4>`); continue; }
    // A line that is entirely bold is a heading in everything but syntax.
    const bold = line.match(/^\*\*(.+?)\*\*:?\s*$/);
    if (bold) { out.push(`<h4>${inline(bold[1])}</h4>`); continue; }
    out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push("</ul>");
  return out.join("");
}

function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|\W)\*(?!\s)(.+?)(?<!\s)\*(?=\W|$)/g, "$1<em>$2</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

/* ---------------------------------------------------------------- explain */

function showExplain(term, body) {
  const sheet = document.createElement("div");
  sheet.className = "sheet";
  sheet.innerHTML = `
    <div class="sheet-card" role="dialog" aria-modal="true">
      <header><h3>${esc(term)}</h3>
        <button class="icon" data-close aria-label="${esc(t("action.close"))}">
          <svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>
        </button>
      </header>
      <h4>${esc(t("explain.what"))}</h4>
      <p>${esc(body)}</p>
    </div>`;
  sheet.addEventListener("click", (e) => {
    if (e.target === sheet || e.target.closest("[data-close]")) sheet.remove();
  });
  document.addEventListener("keydown", function onKey(e) {
    if (e.key === "Escape") { sheet.remove(); document.removeEventListener("keydown", onKey); }
  });
  document.body.appendChild(sheet);
}

/* --------------------------------------------------------------- settings */

async function loadProfile() {
  try {
    const data = await get("/api/profile");
    profile = data.profile;
    setLanguage(profile.language || "en");
    mode = profile.advanced_mode ? "advanced" : "simple";
    renderSettings(data.choices);
  } catch {
    profile = null;
  }
}

async function saveProfile(changes) {
  try {
    const { profile: updated } = await patch("/api/profile", changes);
    profile = updated;
    if (changes.language) setLanguage(updated.language);
    renderSettings();
    if (payload) render();
  } catch (err) {
    console.error(err);
  }
}

const PROFILE_FIELDS = {
  technical_level: ["beginner", "intermediate", "advanced"],
  detail: ["simple", "balanced", "deep", "everything"],
  research_depth: ["quick", "standard", "deep", "full"],
};

function renderSettings() {
  if (!profile) return;

  $("sLanguage").innerHTML = LANGUAGES.map((l) => `
    <button class="chip pickable ${profile.language === l.code ? "on" : ""}"
            data-lang="${l.code}">${esc(l.label)}</button>`).join("");

  for (const [field, values] of Object.entries(PROFILE_FIELDS)) {
    const host = document.querySelector(`[data-profile="${field}"]`);
    if (!host) continue;
    host.innerHTML = values.map((v) => `
      <button class="chip pickable ${profile[field] === v ? "on" : ""}"
              data-field="${field}" data-value="${v}">${esc(t(`a.${v}`))}</button>`).join("");
  }

  $("sProfile").textContent = JSON.stringify(profile, null, 2);
  applyTranslations();
}

/* ------------------------------------------------------------------ wiring */

function wireClicks() {
  document.addEventListener("click", async (e) => {
    const depthBtn = e.target.closest("[data-depth]");
    if (depthBtn) {
      depth = depthBtn.dataset.depth;
      renderDepth();
      if (symbol) await open(symbol);
      return;
    }

    const att = e.target.closest("[data-attention]");
    if (att) {
      const key = att.dataset.attention;
      if (key === "__none") attention = [];
      else attention = attention.includes(key)
        ? attention.filter((a) => a !== key)
        : [...attention, key];
      renderAttention();
      return;
    }

    const seg = e.target.closest("[data-mode]");
    if (seg) {
      mode = seg.dataset.mode;
      document.querySelectorAll("[data-mode]").forEach((b) =>
        b.classList.toggle("active", b.dataset.mode === mode));
      $("rModeHint").textContent = t(mode === "simple" ? "mode.simpleHint" : "mode.advancedHint");
      if (payload) renderSections();
      saveProfile({ advanced_mode: mode === "advanced" });
      return;
    }

    const why = e.target.closest("[data-explain]");
    if (why) { showExplain(why.dataset.term, why.dataset.explain); return; }

    const lang = e.target.closest("[data-lang]");
    if (lang) { saveProfile({ language: lang.dataset.lang }); return; }

    const field = e.target.closest("[data-field]");
    if (field) { saveProfile({ [field.dataset.field]: field.dataset.value }); return; }

    if (e.target.closest("#sReset")) {
      const { profile: reset } = await post("/api/profile/reset", {});
      profile = reset;
      setLanguage(profile.language);
      renderSettings();
      return;
    }
  });

  $("rRun").onclick = runAnalysis;
}

/* --------------------------------------------------------------------- go */

(async () => {
  wireSearch();
  wireClicks();
  await loadProfile();
  depth = (profile && profile.research_depth) || "standard";
  attention = (profile && profile.attention) || [];
  applyTranslations();

  // The mentor endpoint already knows which model is answering; reuse it so
  // Settings doesn't need a second source of truth.
  try {
    const mentor = await get("/api/mentor");
    const ai = mentor.ai || {};
    $("sProvider").textContent = ai.available
      ? `${ai.model || ai.provider}${ai.free ? " · free" : ""}`
      : t("research.noAI");
  } catch { /* the dashboard still works without it */ }
})();
