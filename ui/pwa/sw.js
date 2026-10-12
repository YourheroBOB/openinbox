/* TooPowerInbox service worker: static assets only. Mail data (/api/*) is never cached. */
"use strict";
const VERSION = "__TPI_VERSION__";
const PREFIX = "tpi-static-";
const CACHE = PREFIX + VERSION;
const PRECACHE = __TPI_PRECACHE__;
const OFFLINE = "/offline.html";
const CACHE_FIRST = [
  /^\/offline\.html$/,
  /^\/manifest\.webmanifest$/,
  /^\/icons\/[A-Za-z0-9][\w.-]*\.(png|svg)$/,
  /^\/apple-touch-icon(-precomposed)?\.png$/,
  /^\/favicon\.ico$/,
];
const NETWORK_FIRST = [/^\/ui\/modules\/[A-Za-z0-9][\w-]*\.js$/];

function strategy(request) {
  if (request.method !== "GET") return "";
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return "";
  if (url.pathname.startsWith("/api/")) return "";
  if (request.mode === "navigate") return "navigate";
  if (CACHE_FIRST.some((re) => re.test(url.pathname))) return "cache";
  if (NETWORK_FIRST.some((re) => re.test(url.pathname))) return "network";
  return "";
}

async function store(request, response) {
  if (response && response.ok && response.type === "basic") {
    const cache = await caches.open(CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

async function cacheFirst(request) {
  const hit = await caches.match(request);
  return hit || store(request, await fetch(request));
}

async function networkFirst(request) {
  try {
    return await store(request, await fetch(request));
  } catch (err) {
    const hit = await caches.match(request);
    if (hit) return hit;
    throw err;
  }
}

async function navigate(request) {
  try {
    return await fetch(request);
  } catch (err) {
    const hit = await caches.match(OFFLINE);
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith(PREFIX) && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const kind = strategy(event.request);
  if (kind === "navigate") event.respondWith(navigate(event.request));
  else if (kind === "cache") event.respondWith(cacheFirst(event.request));
  else if (kind === "network") event.respondWith(networkFirst(event.request));
});

self.addEventListener("message", (event) => {
  if (event.data === "tpi-version" && event.source) event.source.postMessage({ type: "tpi-version", version: VERSION, cache: CACHE });
});
