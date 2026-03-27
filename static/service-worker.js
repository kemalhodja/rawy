const CACHE_NAME = 'rawy-v1';
const STATIC_ASSETS = [
  '/app',
  '/static/index.html',
  '/static/manifest.json'
];

// Kurulum - statik dosyaları cache'le
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Aktivasyon - eski cache'leri temizle
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch - cache first, network fallback
self.addEventListener('fetch', (e) => {
  // API isteklerini cache'leme
  if (e.request.url.includes('/voice/') || 
      e.request.url.includes('/auth/') ||
      e.request.url.includes('/reminders/') ||
      e.request.url.includes('/tasks/')) {
    return fetch(e.request).catch(() => {
      // Offline ise placeholder döndür
      return new Response(JSON.stringify({ offline: true }), {
        headers: { 'Content-Type': 'application/json' }
      });
    });
  }
  
  e.respondWith(
    caches.match(e.request).then((response) => {
      return response || fetch(e.request);
    })
  );
});

// Push bildirimleri (hatırlatıcılar için)
self.addEventListener('push', (e) => {
  const data = e.data.json();
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icons/icon-192x192.png',
      badge: '/static/icons/icon-72x72.png',
      tag: data.tag || 'reminder',
      requireInteraction: true,
      actions: [
        { action: 'snooze', title: 'Ertele (5 dk)' },
        { action: 'dismiss', title: 'Tamam' }
      ]
    })
  );
});

// Bildirim tıklama
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  
  if (e.action === 'snooze') {
    // Erteleme işlemi - ana uygulamaya mesaj gönder
    e.waitUntil(
      self.clients.matchAll({ type: 'window' }).then((clients) => {
        if (clients[0]) {
          clients[0].postMessage({ type: 'SNOOZE_REMINDER', tag: e.notification.tag });
        }
      })
    );
  } else if (e.action === 'dismiss') {
    // Kapatma işlemi
    e.waitUntil(
      self.clients.matchAll({ type: 'window' }).then((clients) => {
        if (clients[0]) {
          clients[0].postMessage({ type: 'DISMISS_REMINDER', tag: e.notification.tag });
        }
      })
    );
  } else {
    // Bildirime tıklama - uygulamayı aç
    e.waitUntil(
      self.clients.openWindow('/app')
    );
  }
});
