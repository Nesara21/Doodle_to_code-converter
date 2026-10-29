/**
 * service-worker.js
 * -------------------
 * Minimal PWA service worker for Doodle to Code.
 *
 * Design goals (deliberately conservative, see notes below):
 *   1. Cache only the static app shell (HTML shell, CSS, JS, manifest,
 *      icons) so the UI loads instantly and works offline.
 *   2. NEVER cache /generate/* or /preview/* - those are dynamic,
 *      server-rendered results and must always come from the live
 *      Flask server on this machine.
 *   3. Bump CACHE_NAME whenever you change static files. On activate,
 *      every cache that isn't the current CACHE_NAME is deleted, so
 *      stale versions can't linger and serve old UI - this is the
 *      exact class of bug where an old app's service worker keeps
 *      intercepting requests after you've moved on to a new project
 *      on the same port/origin.
 */

const CACHE_VERSION = "v1";
const CACHE_NAME = `doodle-to-code-${CACHE_VERSION}`;

const APP_SHELL = [
    "/",
    "/static/css/style.css",
    "/static/js/script.js",
    "/manifest.json",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
];

// ---- install: pre-cache the app shell, activate immediately ----
self.addEventListener("install", (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
    );
});

// ---- activate: delete any cache that isn't the current version ----
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

// ---- fetch: network-first for dynamic routes, cache-first for the shell ----
self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    // Only handle same-origin GET requests; let everything else pass through untouched.
    if (event.request.method !== "GET" || url.origin !== self.location.origin) {
        return;
    }

    // Generated/preview output must always be fresh - never served from cache.
    if (url.pathname.startsWith("/generate/") || url.pathname.startsWith("/preview/")) {
        event.respondWith(fetch(event.request));
        return;
    }

    // App shell / static assets: try cache first, fall back to network,
    // and opportunistically cache newly-seen same-origin GET responses.
    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request).then((response) => {
                if (response && response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            });
        })
    );
});
