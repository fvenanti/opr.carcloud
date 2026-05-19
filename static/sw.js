// Service Worker mínimo para habilitar instalación como PWA
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());

// Sin caché offline — la app requiere conexión
self.addEventListener('fetch', event => {
  event.respondWith(fetch(event.request));
});
