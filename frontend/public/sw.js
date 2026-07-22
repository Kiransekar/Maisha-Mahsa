// Hand-rolled service worker (WS7.9 core) — plain JS in public/ so Vite copies it verbatim to
// the build root with zero build-step/config of its own (the boring option: no vite-plugin-pwa,
// no separate webworker tsconfig project). Registered from src/main.tsx.
//
// THE ONE RULE THAT MATTERS (docs/MASTER_PLAN.md §0.4 / WS7_BUILD_CONTRACT T4): a cached ✓
// figure served back as if it were current is a fabricated verification — the exact failure the
// whole product exists to prevent. So this file does the least possible with /api/* traffic:
//
//   · GET  /api/*  → network-first, but with NO cache fallback. If the network fails, the
//     request fails (a real TypeError), same as if this service worker did not exist at all.
//     That failure is what every screen already treats as "stale/unknown, downgrade ✓ to ◐" —
//     see effectiveState() in src/components/VerifiedNumber.tsx and its callers. Teaching this
//     file to instead serve a cached 200 would require inventing a new signal so the app can
//     tell "this 200 is live" from "this 200 is a minute-old cache", and every component would
//     need to consume it. That is real complexity for a benefit (reading stale figures while
//     fully offline) the product explicitly does not want — an unverifiable figure should read
//     as unverified, not as a slightly-old verified one.
//     ponytail: no offline-read cache for API data. Upgrade path if ever wanted: tag the cached
//     fallback response with a header (e.g. `X-Maisha-Cache: stale`), read it in src/lib/api.ts,
//     and thread a `Freshness` of "unknown" through to the caller instead of throwing.
//   · non-GET /api/* (writes)  → not intercepted at all. A write must never be answered from a
//     cache; letting the browser's normal fetch run means an offline write fails exactly like an
//     unreachable server, which is what ErrorState's write-copy already assumes.
//
// Everything else is ordinary PWA plumbing:
//   · GET same-origin /assets/*  → cache-first. Vite content-hashes these filenames, so the same
//     URL is always the same bytes — there is nothing to go stale.
//   · GET navigation requests (the app shell, index.html) → network-first with a cache fallback,
//     so opening the installed app while offline doesn't just fail outright. This carries no
//     figures, so it isn't a §0.4 concern.

const STATIC_CACHE = "maisha-static-v1";
const SHELL_CACHE = "maisha-shell-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  const keep = new Set([STATIC_CACHE, SHELL_CACHE]);
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.has(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never touch writes — including /api/* mutations
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // no opinion on cross-origin requests

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(request)); // network-first, no fallback — see file header
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstShell(request));
  }
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const res = await fetch(request);
  if (res.ok) (await caches.open(cacheName)).put(request, res.clone());
  return res;
}

async function networkFirstShell(request) {
  try {
    const res = await fetch(request);
    if (res.ok) (await caches.open(SHELL_CACHE)).put(request, res.clone());
    return res;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw err;
  }
}
