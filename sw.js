const CACHE_NAME = "savings-stocks-v4";
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

  // ÖNEMLİ: sade fetch(event.request) tarayıcının KENDİ http önbelleğine
  // (GitHub Pages'in Cache-Control başlığına göre) düşebiliyor ve ağa hiç
  // gitmeden eski bir kopyayı geri verebiliyordu. cache:"no-store" ile bu
  // katmanı da tamamen devre dışı bırakıp her zaman gerçekten ağdan taze
  // dosyayı istiyoruz; olmazsa (offline ise) service worker'ın kendi
  // önbelleğine düşüyoruz.
  const freshRequest = new Request(event.request.url, { cache: "no-store" });

  // data.json: her zaman ağdan taze veri dene, olmazsa önbelleğe düş.
  if (url.pathname.endsWith("data.json")) {
    event.respondWith(
      fetch(freshRequest)
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
    fetch(freshRequest)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
