const CACHE_NAME = 'traitkeeper-cache-v1';
const urlsToCache = [
  "/",
  "/static/css/styles/main.css",
  // wallet javascripts
  "/static/js/src/wallet-connection.js",
  "/static/img/Trait-Keeper-Logo-purple-1-unaimated-effect.png",
];

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
});

self.addEventListener('fetch', function (event) {
  event.respondWith(
    caches.match(event.request)
      .then(function (response) {
        if (response) {
          return response;
        }
        return fetch(event.request).then(
          function (response) {
            // Check if we received a valid response
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }

            // IMPORTANT: Clone the response. A response is a stream
            // and because we want the browser to consume the response
            // as well as the cache consuming the response, we need
            // to clone it so we have two streams.
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
        // You can add fallback content here
      })
  );
});