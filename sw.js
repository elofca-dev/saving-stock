const CACHE_NAME = "savings-stocks-v3";
const CORE_ASSETS = ["./", "./index.html", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;

  // data.json: her zaman ağdan taze veri dene, olmazsa önbelleğe düş.
  if (url.pathname.endsWith("data.json")) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Diğer statik dosyalar (index.html, manifest.json, icon.svg vb.):
  // önce ağdan taze sürümü dene, olmazsa (offline ise) önbelleğe düş.
  // Böylece yeni bir kod değişikliği yayınlandığında kullanıcı bir sonraki
  // açılışta hemen güncel sürümü görür; eski "önbellek öncelikli" strateji
  // yeni özelliklerin görünmesini bir uygulama daha geciktiriyordu.
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
