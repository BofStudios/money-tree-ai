/* Money Tree service worker.
 *
 * Its main job is to make the dashboard installable as a phone app. It is
 * deliberately conservative about caching, because a trading screen showing
 * yesterday's numbers as if they were live is worse than showing nothing:
 *
 *   /api/*   never cached, never served from cache — always the network.
 *   the UI   network first; the cached copy is used only when offline, so a
 *            new build shows up on the next load instead of hiding behind
 *            a stale cache.
 */

const CACHE = "mt-shell-v2";
const SHELL = [
  "/", "/index.html", "/dashboard.css", "/research.css",
  "/chart.js", "/research.js", "/home.js", "/home.css", "/i18n.js", "/logo.png",
  "/vendor/lightweight-charts.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => { /* a missing file must not block install */ })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  // Market and account data: straight to the network, no fallback.
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(url.pathname, copy));
        }
        return response;
      })
      .catch(() => caches.match(url.pathname).then((hit) => hit || caches.match("/")))
  );
});
