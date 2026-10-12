/* Ultra mode: the switch, the warning, and the red edge it puts on everything.
 *
 * Turning it on always shows the warning first and needs a tick: it uses the
 * whole computer. Turning it off is one click. Ultra never touches Stop, the
 * arming of real money or the risk limits — those stay exactly as they are.
 */

import { t } from "/i18n.js";

const $ = (id) => document.getElementById(id);
const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("token");
  try { return fromUrl || localStorage.getItem("mt_token") || ""; } catch { return fromUrl || ""; }
})();
const q = (p) => (TOKEN ? `${p}${p.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}` : p);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let on = false;

async function setUltra(value) {
  const res = await fetch(q("/api/brain/settings"), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ultra: value }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  apply(value);
  window.showAlert?.({ tone: value ? "bad" : "good", title: t(value ? "ultra.onAlert" : "ultra.offAlert") });
}

function apply(value) {
  on = !!value;
  document.body.classList.toggle("ultra", on);
  const badge = $("ultraBadge");
  if (badge) badge.hidden = !on;
  const btn = $("ultraToggle");
  if (btn) {
    btn.textContent = t(on ? "ultra.turnOff" : "ultra.turnOn");
    btn.classList.toggle("is-on", on);
  }
  const state = $("ultraState");
  if (state) state.textContent = t(on ? "ultra.stateOn" : "ultra.stateOff");
}

function warn() {
  const box = $("ultraModal");
  box.hidden = false;
  box.innerHTML = `
    <div class="confirm-card ultra-warning">
      <div class="ultra-warning-head"><span class="ultra-mark">ULTRA</span><b>${esc(t("ultra.warnTitle"))}</b></div>
      <p>${esc(t("ultra.warnBody"))}</p>
      <ul class="ultra-list">
        <li>${esc(t("ultra.w1"))}</li><li>${esc(t("ultra.w2"))}</li><li>${esc(t("ultra.w3"))}</li>
        <li>${esc(t("ultra.w4"))}</li><li>${esc(t("ultra.w5"))}</li>
      </ul>
      <label class="ultra-agree"><input type="checkbox" id="ultraAgree"> ${esc(t("ultra.agree"))}</label>
      <div class="onboard-actions">
        <button class="ultra-btn" id="ultraGo" disabled>${esc(t("ultra.go"))}</button>
        <button class="ghost" id="ultraCancel">${esc(t("ultra.cancel"))}</button>
      </div>
      <p class="note bad" id="ultraError"></p>
    </div>`;
  $("ultraAgree").onchange = (e) => { $("ultraGo").disabled = !e.target.checked; };
  $("ultraCancel").onclick = () => { box.hidden = true; };
  $("ultraGo").onclick = async () => {
    $("ultraGo").disabled = true;
    try { await setUltra(true); box.hidden = true; } catch (err) { $("ultraError").textContent = err.message; }
  };
}

document.addEventListener("click", async (e) => {
  if (e.target.closest("#ultraToggle")) {
    if (on) {
      try { await setUltra(false); } catch (err) { window.showAlert?.({ tone: "bad", title: err.message }); }
    } else {
      warn();
    }
  }
  if (e.target.closest("#ultraBadge")) window.showView?.("settings");
});

window.addEventListener("mt:status", (e) => {
  const s = e.detail || window.mtState || {};
  if (typeof s.ultra === "boolean" && s.ultra !== on) apply(s.ultra);
});
window.addEventListener("mt:lang", () => apply(on));
apply(false);
