/* Money Bot 12.0 shell: six groups over the existing views (B1.2).
 *
 * The views themselves are unchanged: chart.js's showView() still switches
 * them and still announces "mt:view" with the old names, which the older
 * modules listen for. This file only maps a view to its group, marks the
 * group, shows that group's sub-tabs and remembers the last view per group.
 */

const GROUPS = {
  bot: ["bot"],
  market: ["chart", "market", "news", "catalysts", "research"],
  portfolio: ["portfolio", "money"],
  lab: ["lab", "swarm", "brain", "modes"],
  settings: ["settings"],
};
const GROUP_OF = Object.fromEntries(Object.entries(GROUPS).flatMap(([g, vs]) => vs.map((v) => [v, g])));
const DESKTOP = window.matchMedia("(min-width: 1100px)");

let last = {};
try { last = JSON.parse(localStorage.getItem("mb_last_view") || "{}") || {}; } catch { last = {}; }

function mark(view) {
  const group = GROUP_OF[view] || "bot";
  document.body.dataset.group = group;
  document.querySelectorAll("#nav .grp").forEach((b) => {
    if (b.dataset.group === "chat") return;
    if (b.dataset.group === group) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  document.querySelectorAll("#mbSub .mb-subset").forEach((set) => { set.hidden = set.dataset.sub !== group; });
  document.querySelectorAll("#mbSub button.sub").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === view)));
  last[group] = view;
  try { localStorage.setItem("mb_last_view", JSON.stringify(last)); } catch { /* storage off */ }
}

function go(group) {
  const views = GROUPS[group];
  if (!views) return;
  const view = views.includes(last[group]) ? last[group] : views[0];
  if (window.showView) window.showView(view);
}

function chat() {
  const btn = document.querySelector('#nav .grp[data-group="chat"]');
  if (DESKTOP.matches) {
    const open = !document.body.classList.contains("mb-chat");
    document.body.classList.toggle("mb-chat", open);
    btn.setAttribute("aria-pressed", String(open));
    if (open) document.getElementById("askInput")?.focus();
  } else if (window.openAI) {
    window.openAI(true);
  }
}

document.getElementById("nav").addEventListener("click", (e) => {
  const b = e.target.closest(".grp");
  if (!b) return;
  if (b.dataset.group === "chat") chat(); else go(b.dataset.group);
});

document.addEventListener("click", (e) => {
  const sub = e.target.closest("#mbSub button.sub");
  if (sub && window.showView) { window.showView(sub.dataset.tab); return; }
  const home = e.target.closest("[data-group-go]");
  if (home) go(home.dataset.groupGo);
});

window.addEventListener("mt:view", (e) => mark(e.detail));
mark("bot");
document.querySelector('#nav .grp[data-group="chat"]')?.setAttribute("aria-pressed", "false");
