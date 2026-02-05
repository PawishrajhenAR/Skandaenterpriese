// Service Worker for Skanda - static frontend paths
const CACHE_NAME = 'skanda-v1.0.1';
const STATIC_CACHE_NAME = 'skanda-static-v1.0.1';
const DYNAMIC_CACHE_NAME = 'skanda-dynamic-v1.0.1';

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/style.css',
  '/css/calendar.css',
  '/js/main.js',
  '/js/api.js',
  '/js/config.js',
  '/icons/icon-192x192.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n.startsWith('skanda-') && n !== STATIC_CACHE_NAME && n !== DYNAMIC_CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== location.origin && !url.href.includes('cdn.jsdelivr.net') && !url.href.includes('fonts.googleapis.com')) return;

  if (event.request.url.match(/\.(css|js|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot|ico)$/)) {
    event.respondWith(
      caches.match(event.request).then((c) => c || fetch(event.request).then((r) => {
        if (r.ok) caches.open(DYNAMIC_CACHE_NAME).then((cache) => cache.put(event.request, r.clone()));
        return r;
      }))
    );
  } else {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request).then((c) => c || caches.match('/index.html')))
    );
  }
});
