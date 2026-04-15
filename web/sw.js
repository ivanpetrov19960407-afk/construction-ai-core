const CACHE_NAME = "construction-ai-web-v1";
const URLS_TO_CACHE = [
  "/web/",
  "/web/index.html",
  "/web/styles.css",
  "/web/app.js",
  "/web/manifest.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(URLS_TO_CACHE)));
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => cachedResponse || fetch(event.request))
  );
});
