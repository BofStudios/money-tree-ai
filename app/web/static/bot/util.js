/* Shared helpers for the Bot console: escaping, words, money and time. */

import { getLanguage, t } from "/i18n.js";

export const $ = (id) => document.getElementById(id);

/** Every server text goes through this before it touches innerHTML. */
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const T = (key, vars) => t(`bot.${key}`, vars);
export const lang = () => getLanguage();
const locale = () => (getLanguage() === "tr" ? "tr-TR" : "en-US");

const MINUS = "−";
let nf = null; let nfLocale = "";
function usd() {
  if (nfLocale !== locale()) {
    nfLocale = locale();
    nf = new Intl.NumberFormat(nfLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return nf;
}

/** $1,234.56 ; −$3.42 ; +$1.10 with sign:true. null -> "—". */
export function money(v, { sign = false } = {}) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const body = `$${usd().format(Math.abs(n))}`;
  if (n < 0) return MINUS + body;
  return sign && n > 0 ? `+${body}` : body;
}

export function pct(v, { sign = true } = {}) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const body = `${usd().format(Math.abs(n))}%`;
  if (n < 0) return MINUS + body;
  return sign && n > 0 ? `+${body}` : body;
}

export const tone = (v) => (v > 0 ? "good" : v < 0 ? "bad" : "flat");

export function int(v) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat(locale()).format(v);
}

const two = (n) => String(n).padStart(2, "0");
export function hms(ms) {
  const d = new Date(ms);
  return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}
export function nyTime(ms) {
  try {
    return new Date(ms).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false }) + " NY";
  } catch { return ""; }
}

/** "now", "4 min ago", "2 h ago" — from the server's timestamp, never guessed. */
export function ago(ms, now = Date.now()) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 45) return T("ago.now");
  const m = Math.round(s / 60);
  if (m < 60) return T("ago.min", { n: m });
  const h = Math.round(m / 60);
  if (h < 48) return T("ago.h", { n: h });
  return T("ago.d", { n: Math.round(h / 24) });
}

export function minutes(n) {
  if (n === null || n === undefined) return "—";
  return n < 60 ? T("dur.min", { n }) : T("dur.h", { h: Math.floor(n / 60), m: n % 60 });
}

export async function api(method, path, body) {
  const res = await fetch(path, {
    method, credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const glyph = (id) => `<svg class="mb-glyph" viewBox="0 0 20 20" aria-hidden="true"><use href="/bot/glyphs.svg#g-${esc(id)}"/></svg>`;
