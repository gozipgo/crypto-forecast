// 오프라인 대비용 서비스 워커. 항상 네트워크 우선(최신 데이터·화면), 실패할 때만 캐시.
const CACHE = 'cf-v2';
const SHELL = ['./', 'index.html', 'style.css', 'app.js', 'chart.js', 'fan-primitive.js',
  'vendor/lightweight-charts.standalone.production.js', 'manifest.webmanifest', 'icons/icon-192.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith((async () => {
    try {
      const res = await fetch(req, { cache: 'no-cache' });
      if (res.ok) {
        const c = await caches.open(CACHE);
        c.put(new URL(req.url).pathname.includes('/data/') ? new Request(req.url.split('?')[0]) : req, res.clone());
      }
      return res;
    } catch (err) {
      const hit = (await caches.match(req)) || (await caches.match(req.url.split('?')[0]));
      if (hit) return hit;
      throw err;
    }
  })());
});
