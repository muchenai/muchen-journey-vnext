const CACHE_NAME = "muchen-journey-entry-v3";
const CACHE_PREFIX = "muchen-journey-entry-";
const CACHEABLE_PREFIXES = ["/_next/static/", "/assets/project9/", "/fonts/project9/", "/images/", "/journey/", "/vendor/feishu/"];

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME).map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !CACHEABLE_PREFIXES.some(prefix => url.pathname.startsWith(prefix))) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    if (["localhost", "127.0.0.1"].includes(url.hostname)) {
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        const cached = await cache.match(request);
        if (cached) return cached;
        throw new Error("LOCAL_RESOURCE_UNAVAILABLE");
      }
    }
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  })());
});
