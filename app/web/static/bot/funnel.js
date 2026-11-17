/* Why trades happen or not (B2.20–B2.21): five steps on a log scale so 18,240
   and 5 fit one row, the number always written; the gates that cut most; and,
   on a day with no fills, one sentence built only from the server's numbers. */

import { $, T, esc, int } from "./util.js";
import { store, setTab } from "./store.js";

const host = $("mbFunnel");

function draw() {
  if (!host) return;
  const f = (store.snap && store.snap.funnel) || {};
  const steps = f.steps || [];
  const blocked = [...(f.blocked || [])].sort((a, b) => b.n - a.n);
  const fills = (steps.find((s) => s.id === "fills") || {}).n;
  const signals = (steps.find((s) => s.id === "signals") || {}).n;
  const quiet = steps.length && !fills;
  host.classList.toggle("mb-quiet", !!quiet);

  if (!steps.length) {
    host.innerHTML = `<span class="mb-box-label">${esc(T("funnel.title"))}</span><p class="mb-dim">${esc(T("funnel.empty"))}</p>`;
    return;
  }
  const max = Math.max(...steps.map((s) => s.n), 1);
  const w = (n) => (n > 0 ? 18 + 82 * (Math.log10(n + 1) / Math.log10(max + 1)) : 18);
  let sentence = "";
  if (quiet && signals) {
    const top = blocked[0];
    const cut = blocked.reduce((a, b) => a + b.n, 0);
    sentence = top ? T("funnel.quiet", { n: int(signals), cut: int(cut), gate: top.label, k: int(top.n) }) : T("funnel.quietNoGate", { n: int(signals) });
  }
  host.innerHTML = `<span class="mb-box-label">${esc(T("funnel.title"))}</span>
    ${sentence ? `<p class="mb-funnel-say">${esc(sentence)}</p>` : ""}
    <ol class="mb-steps">${steps.map((s) => `<li><i style="width:${w(s.n).toFixed(1)}%" aria-hidden="true"></i><b class="num">${esc(int(s.n))}</b><span>${esc(s.label)}</span></li>`).join("")}</ol>
    ${blocked.length ? `<ul class="mb-gates">${blocked.slice(0, 4).map((g) => `<li><button type="button" data-gate="${esc(g.gate)}" data-agent="${esc(g.by || "")}">
      <span>${esc(g.label)}</span><b class="num">${esc(int(g.n))}</b><em>${esc(g.by || "")}</em></button></li>`).join("")}</ul>` : ""}`;
}

window.addEventListener("bot:update", ({ detail: { changed } }) => {
  if (changed.has("snap") || changed.has("all")) draw();
});

host?.addEventListener("click", (e) => {
  // A gate opens the risk tab, where its vetoes are listed.
  if (e.target.closest("[data-gate]")) setTab("risk");
});
