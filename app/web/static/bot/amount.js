/* Real money is the only way (owner's decision, 12.0). Two things at the top
 * of the console:
 *
 *   setup strip  one step at a time from setup.next: keys -> live -> amount -> arm.
 *                "live" reuses money.js's typed confirmation (data-set-mode).
 *                Arm stays the owner's own click in the top bar, every start.
 *   amount       how much the bot may use, typed by the owner (= risk.budget,
 *                POST /api/bot/risk {budget}). Lowering it is immediate; raising
 *                it on a real account answers 409 and needs a second click.
 */

import { $, T, esc, money, api } from "./util.js";
import { store, loadSnap } from "./store.js";

const host = $("mbAmount");
let typed = null;          // what the owner is typing (string), null = show the server's value
let pending = null;        // a body waiting for the second click
let note = null;           // {tone, text}
let busy = false;

/** setup from the server, or the same steps worked out from what it already says. */
function setup(s) {
  if (s.setup) return s.setup;
  const live = !!(s.account && s.account.mode === "live");
  const amount = !!(s.risk && s.risk.budget != null);
  const next = !live ? "keys" : !amount ? "amount" : !(s.account && s.account.armed) ? "arm" : null;
  return { keys: live, live, amount, next };
}

function strip(st) {
  if (!st.next) return "";
  const steps = ["keys", "live", "amount", "arm"];
  const at = steps.indexOf(st.next);
  const dots = steps.map((k, i) => `<li class="${i < at ? "is-done" : i === at ? "is-now" : ""}">${esc(T(`setup.step.${k}`))}</li>`).join("");
  const action = st.next === "keys"
    ? `<button class="mb-btn mb-ok" type="button" data-setup="keys">${esc(T("setup.keysBtn"))}</button>`
    : st.next === "live"
      ? `<button class="mb-btn mb-ok" type="button" data-set-mode="live">${esc(T("setup.liveBtn"))}</button>`
      : st.next === "amount"
      ? `<button class="mb-btn mb-ok" type="button" data-setup="amount">${esc(T("setup.amountBtn"))}</button>`
      : "";
  return `<div class="mb-setup" role="status"><ol>${dots}</ol><p>${esc(T(`setup.${st.next}`))}</p>${action}</div>`;
}

function draw() {
  if (!host) return;
  const s = store.snap;
  if (!s) { host.innerHTML = ""; return; }
  const st = setup(s);
  // Before the real account is connected the log, crew and panels would show the
  // background practice engine; only the setup strip and the amount are shown.
  host.closest(".mb-console")?.classList.toggle("mb-unready", !st.live);
  const budget = s.risk ? s.risk.budget : null;
  const equity = s.tiles && s.tiles.capital ? s.tiles.capital.equity : null;
  const value = typed !== null ? typed : budget != null ? String(budget) : "";
  const changed = typed !== null && Number(typed) !== Number(budget);
  const focused = host.contains(document.activeElement) && document.activeElement.id === "mbAmountIn";

  if (focused) {   // typing: leave the input alone, refresh the rest
    host.querySelector(".mb-amount-save").disabled = busy || !changed || !(Number(typed) > 0);
    return;
  }
  host.innerHTML = `${strip(st)}
    <form class="mb-amount-form" novalidate>
      <label for="mbAmountIn">${esc(T("amount.label"))}</label>
      <div class="mb-amount-row">
        <span class="mb-amount-cur num" aria-hidden="true">$</span>
        <input id="mbAmountIn" class="mb-amount-in num" type="number" inputmode="decimal" min="1" step="1"
          value="${esc(value)}" placeholder="0" ${st.live ? "" : "disabled"} aria-describedby="mbAmountSay">
        <button class="mb-btn mb-ok mb-amount-save" type="submit" ${busy || !changed || !(Number(typed) > 0) ? "disabled" : ""}>${esc(T("amount.save"))}</button>
        ${budget != null && st.live ? `<button class="mb-btn mb-amount-all" type="button" data-amount-all ${busy ? "disabled" : ""}>${esc(T("amount.all"))}</button>` : ""}
        ${pending ? `<button class="mb-btn mb-warnbtn" type="button" data-amount-confirm>${esc(T("amount.confirm"))}</button>` : ""}
      </div>
      <p class="mb-amount-say" id="mbAmountSay">${esc(!st.live ? T("amount.noKeys")
        : budget == null ? T("amount.none")
          : T("amount.of", { v: money(budget), e: money(equity) }))}</p>
      ${note ? `<p class="mb-note ${note.tone === "ok" ? "ok" : ""}">${esc(note.text)}</p>` : ""}
    </form>${st.live ? "" : intro(s)}`;
}

/** Before the real account: what the bot is, in four plain lines, and the Lab's honest number. */
function intro(s) {
  const p = s.proof || {};
  const pct = typeof p.per_trade_pct === "number" ? `${p.per_trade_pct >= 0 ? "+" : ""}${p.per_trade_pct.toFixed(3)}%` : null;
  const lab = pct && (p.state === "lost" || p.state === "passed")
    ? `<p class="mb-intro-lab" data-state="${esc(p.state)}">${esc(T(`intro.${p.state}`, { v: pct }))}</p>` : "";
  return `<section class="mb-intro" aria-label="Money Bot">
      <h2>${esc(T("intro.title"))}</h2>
      <ul>
        <li>${esc(T("intro.crew"))}</li>
        <li>${esc(T("intro.amount"))}</li>
        <li>${esc(T("intro.stop"))}</li>
      </ul>${lab}
    </section>`;
}

async function save(body) {
  busy = true; draw();
  try {
    const res = await api("POST", "/api/bot/risk", body);
    pending = null; typed = null;
    note = Array.isArray(res.clamped) && res.clamped.includes("budget")
      ? { tone: "warn", text: T("amount.clamped", { v: money(res.values ? res.values.budget : null) }) }
      : { tone: "ok", text: T("amount.saved") };
  } catch (err) {
    if (err.status === 409) { pending = { ...body, confirm: true }; note = { tone: "warn", text: err.message }; }
    else note = { tone: "warn", text: T("amount.failed", { why: err.message }) };
  }
  busy = false;
  await loadSnap();
  draw();
}

host?.addEventListener("input", (e) => {
  if (e.target.id !== "mbAmountIn") return;
  typed = e.target.value; pending = null; note = null;
  draw();
});
host?.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = Number(typed);
  if (busy || !(v > 0)) return;
  save({ budget: v });
});
host?.addEventListener("click", (e) => {
  if (e.target.closest("[data-amount-confirm]") && pending) { save(pending); return; }
  if (e.target.closest("[data-amount-all]")) { save({ budget: null }); return; }   // no limit: the whole account
  const go = e.target.closest("[data-setup]");
  if (!go) return;
  if (go.dataset.setup === "amount") { $("mbAmountIn")?.focus(); return; }
  // Keys are entered in Settings by the owner; never pasted into a chat or a file.
  if (window.showView) window.showView("settings");
  setTimeout(() => $("sMoney")?.scrollIntoView({ block: "start" }), 50);
});

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("all")) draw();
});
