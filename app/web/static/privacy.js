/* Privacy and data (desktop 10.1), in Settings.
 *
 *   Security   phone access (off for a new install), a new dashboard password
 *   AI         what the AI may see of the account, chat memory, screenshots to Gemini,
 *              and "what was the AI last sent"
 *   Servers    every server the app talks to, from the same list a test checks
 *   Data       your files, export, clear, delete what it keeps about you
 *
 * Every number and word comes from /api/privacy: the page decides nothing.
 */

import { getLanguage, t } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

const tr = () => getLanguage() === "tr";
const T = (k, vars) => t(`priv.${k}`, vars);
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

let view = "home";
let state = null;
let note = "";
let restartNeeded = false;
let pendingClear = null;       // the group waiting for a second click
let timer = null;

/* ------------------------------------------------------------------ draw */

function levels() {
  const cur = state.choices.ai_level;
  return state.options.ai_levels.map((l) => `
    <label class="priv-opt ${cur === l ? "on" : ""}">
      <input type="radio" name="privLevel" value="${esc(l)}" ${cur === l ? "checked" : ""}>
      <span><b>${esc(T(`lvl.${l}`))}</b><small>${esc(T(`lvl.${l}Hint`))}</small></span>
    </label>`).join("");
}

function toggle(id, on, label, hint) {
  return `<label class="gate"><input type="checkbox" id="${id}" ${on ? "checked" : ""}>
    <span class="switch"></span><span><b>${esc(label)}</b><small>${esc(hint)}</small></span></label>`;
}

function hostsHtml() {
  // The official newsrooms and feeds share one sentence: they get one row.
  const order = ["always", "keys", "update", "local", "library", "link"];
  const groups = new Map();
  for (const h of state.hosts) {
    const key = `${h.when}|${tr() ? h.wat : h.what}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(h);
  }
  const list = [...groups.values()].sort((a, b) =>
    order.indexOf(a[0].when) - order.indexOf(b[0].when) || a[0].who.localeCompare(b[0].who));
  const row = (hs) => {
    const first = hs[0];
    const many = hs.length > 3;
    const who = many ? hs.map((h) => h.who).sort().join(", ") : first.who;
    const small = many ? `${hs.length} ${T("addresses")}` : first.host;
    return `<tr><th>${esc(who)}<small>${esc(small)}</small></th>
      <td>${esc(tr() ? first.wat : first.what)}${first.policy && !many ? ` <a href="${esc(first.policy)}" target="_blank" rel="noopener noreferrer">${esc(T("theirPolicy"))}</a>` : ""}</td>
      <td><span class="priv-when w-${esc(first.when)}">${esc(T(`when.${first.when}`))}</span></td></tr>`;
  };
  return `<div class="priv-table"><table><tbody>${list.map(row).join("")}</tbody></table></div>`;
}

function filesHtml() {
  return `<div class="priv-table"><table><tbody>${state.files.filter((f) => f.exists).map((f) => `
    <tr><th>${esc(f.path)}${f.secret ? ` <em class="priv-secret">${esc(T("secret"))}</em>` : ""}</th>
      <td>${esc(tr() ? f.tr : f.en)}</td>
      <td class="num">${esc(size(f.bytes))}${f.in_export ? `<small>${esc(T("inExport"))}</small>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

function clearButtons() {
  return ["chat", "learned", "lab", "logs"].map((g) => `
    <button class="ghost sm ${pendingClear === g ? "danger" : ""}" data-clear="${g}">
      ${esc(pendingClear === g ? T("sure") : `${T("clear")}: ${T(`group.${g}`)}`)}</button>`).join("");
}

function render() {
  const body = $("privacyBody");
  if (!body) return;
  if (!state) { body.innerHTML = ""; return; }
  const c = state.choices;
  const ask = state.phone.on && !state.phone.asked;
  body.innerHTML = `
    <div class="block-head"><h2>${esc(T("title"))}</h2></div>
    <p class="note">${esc(T("promise"))} <a class="link-accent" href="/privacy.html" target="_blank" rel="noopener">${esc(T("policy"))}</a></p>
    ${note ? `<p class="note priv-note" role="status">${esc(note)}</p>` : ""}

    <h3>${esc(T("security"))}</h3>
    ${ask ? `<div class="priv-ask"><b>${esc(T("phoneAsk"))}</b>
      <div class="actions"><button class="primary sm" data-phone="1">${esc(T("keepOn"))}</button>
      <button class="ghost sm" data-phone="0">${esc(T("turnOff"))}</button></div></div>` : ""}
    ${toggle("privLan", c.lan, T("phone"), T("phoneHint"))}
    ${restartNeeded ? `<p class="note priv-note">${esc(T("restartNote"))} <button class="primary sm" id="privRestart">${esc(T("restart"))}</button></p>` : ""}
    <p class="note faint">${esc(T("passwordHint"))}</p>
    <div class="actions"><button class="ghost sm" id="privPassword">${esc(T("password"))}</button></div>

    <h3>${esc(T("ai"))}</h3>
    <p class="note faint">${esc(T("aiHint"))}</p>
    <div class="priv-opts">${levels()}</div>
    ${toggle("privRemember", c.remember_chat, T("remember"), T("rememberHint"))}
    ${toggle("privGemini", c.gemini_images, T("gemini"), T("geminiHint"))}
    <details class="priv-seen" id="privSeen"><summary>${esc(T("seen"))}</summary><div id="privSeenBody" class="priv-seen-body"></div></details>

    <details class="priv-fold"><summary>${esc(T("hosts"))} (${state.hosts.length})</summary>
      <p class="note faint">${esc(T("hostsHint"))}</p>
      ${hostsHtml()}
    </details>

    <h3>${esc(T("data"))}</h3>
    <p class="note faint">${esc(T("dataHint"))}</p>
    <p class="path">${esc(state.home)}</p>
    ${filesHtml()}
    <div class="actions">
      <button class="ghost sm" id="privOpen">${esc(T("open"))}</button>
      <button class="primary sm" id="privExport">${esc(T("export"))}</button>
      <label class="priv-days">${esc(T("logDays"))}
        <select id="privDays">${state.options.log_days.map((d) => `<option value="${d}" ${c.log_days === d ? "selected" : ""}>${esc(T("days", { n: d }))}</option>`).join("")}</select></label>
    </div>
    <div class="actions">${clearButtons()}</div>
    <div class="priv-all">
      <b>${esc(T("all"))}</b><small>${esc(T("allHint"))}</small>
      <div class="actions"><input id="privAllWord" autocomplete="off" spellcheck="false" placeholder="${esc(T("allWord"))}">
        <button class="ghost sm danger" id="privAllGo">${esc(T("allGo"))}</button></div>
    </div>
    <p class="note faint">${esc(T("keysNote"))}</p>
    <p class="note faint priv-about">${esc(T("about", { v: state.version }))}
      <a href="https://github.com/BofStudios/money-tree-ai" target="_blank" rel="noopener noreferrer">${esc(T("source"))}</a></p>`;
}

/* ------------------------------------------------------------------ data */

async function load() {
  try { state = await api("GET", "/api/privacy"); } catch (err) { note = err.message; }
  render();
}

function say(text) {
  note = text;
  render();
  clearTimeout(timer);
  timer = setTimeout(() => { note = ""; render(); }, 6000);
}

async function choose(change) {
  try {
    const r = await api("PATCH", "/api/privacy", change);
    state.choices = r.choices;
    state.phone.on = r.choices.lan;
    state.phone.asked = true;
    if (r.restart_needed) restartNeeded = true;
    say(T("saved"));
  } catch (err) { say(err.message); load(); }
}

document.addEventListener("change", (e) => {
  const el = e.target;
  if (!el.closest || !el.closest("#privacyBody")) return;
  if (el.id === "privLan") choose({ lan: el.checked });
  else if (el.id === "privRemember") choose({ remember_chat: el.checked });
  else if (el.id === "privGemini") choose({ gemini_images: el.checked });
  else if (el.id === "privDays") choose({ log_days: Number(el.value) });
  else if (el.name === "privLevel") choose({ ai_level: el.value });
});

document.addEventListener("click", async (e) => {
  const el = e.target.closest ? e.target.closest("#privacyBody button, #privacyBody summary") : null;
  if (!el) return;
  try {
    if (el.dataset.phone !== undefined) return choose({ lan: el.dataset.phone === "1" });
    if (el.id === "privRestart") { await api("POST", "/api/privacy/restart"); return; }
    if (el.id === "privPassword") { const r = await api("POST", "/api/privacy/password"); return say(r.message || T("passwordDone")); }
    if (el.id === "privOpen") { await api("POST", "/api/privacy/open"); return; }
    if (el.id === "privExport") { const r = await api("POST", "/api/privacy/export"); return say(T("exported", { path: r.path })); }
    if (el.dataset.clear) {
      if (pendingClear !== el.dataset.clear) { pendingClear = el.dataset.clear; render(); setTimeout(() => { pendingClear = null; render(); }, 4000); return; }
      pendingClear = null;
      await api("POST", "/api/privacy/clear", { group: el.dataset.clear });
      say(T("cleared"));
      return load();
    }
    if (el.id === "privAllGo") {
      await api("POST", "/api/privacy/clear", { group: "all", confirm: $("privAllWord").value });
      say(T("cleared"));
      return load();
    }
    if (el.tagName === "SUMMARY" && el.parentElement.id === "privSeen" && !el.parentElement.open) {
      const r = await api("GET", "/api/privacy/ai-last");
      const list = r.last || [];
      $("privSeenBody").innerHTML = list.length
        ? `<p class="note faint">${esc(T("seenNote"))}</p>` + list.map((m) => `
            <details class="priv-sent"><summary>${esc(m.at)} · ${esc(m.provider)} ${esc(m.model || "")}</summary>
              <pre>${esc(m.text)}</pre></details>`).join("")
        : `<p class="note faint">${esc(T("seenNone"))}</p>`;
    }
  } catch (err) { say(err.message); }
});

window.addEventListener("mt:view", (e) => { view = e.detail; if (view === "settings") load(); });
window.addEventListener("mt:lang", () => { if (view === "settings") render(); });
