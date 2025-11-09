// TraitKeeper Service Worker - v1
const CACHE_NAME = 'traitkeeper-cache-v1';
const urlsToCache = [
  "/",
  "/static/css/styles/main.css",
  "/static/js/src/wallet-connection.js",
  "/static/img/Trait-Keeper-Logo-purple-1-unaimated-effect.png",
  "/static/img/favicon/android-chrome-192x192.png",
  "/static/img/favicon/android-chrome-512x512.png"
];

// Install event - cache essential files
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function (cache) {
        console.log('Opened cache');
        return cache.addAll(urlsToCache).catch(error => {
          console.error('Failed to cache all resources:', error);
          // Partially cache what we can
          return Promise.all(
            urlsToCache.map(url => {
              return cache.add(url).catch(err => {
                console.warn('Failed to cache:', url, err);
              });
            })
          );
        });
      })
  );
  // Force the waiting service worker to become the active service worker
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', function(event) {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  // Claim clients immediately
  return self.clients.claim();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', function (event) {
  event.respondWith(
    caches.match(event.request)
      .then(function (response) {
        // Cache hit - return response
        if (response) {
          return response;
        }

        return fetch(event.request).then(
          function (response) {
            // Check if we received a valid response
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }

            // Clone the response for caching
            var responseToCache = response.clone();

            caches.open(CACHE_NAME)
              .then(function (cache) {
                cache.put(event.request, responseToCache);
              });

            return response;
          }
        );
      }).catch(function (error) {
        console.error('Fetching failed:', error);
        // Return offline fallback if available
        return caches.match('/');
      })
  );
});

// Handle messages from clients
self.addEventListener('message', function(event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
