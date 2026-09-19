'use strict';
const CACHE_NAME = 'asas-lims-pwa-v9-0-0-runtime-fix';
const APP_SHELL = ['./','./index.html','./style.css?v=9-0-0-runtime-fix','./app-password.js?v=9-0-0-runtime-fix','./branch-map.js?v=9-0-0-runtime-fix','./i18n.js?v=9-0-0-runtime-fix','./runtime-config.js?v=9-0-0-runtime-fix','./asas_tests_module.js?v=9-0-0-runtime-fix','./manifest.webmanifest','./logo.jpg'];
self.addEventListener('install', function(event) {
  event.waitUntil(caches.open(CACHE_NAME).then(function(cache) { return cache.addAll(APP_SHELL); }).then(function() { return self.skipWaiting(); }));
});
self.addEventListener('activate', function(event) {
  event.waitUntil(caches.keys().then(function(keys) {
    return Promise.all(keys.filter(function(key) { return key.startsWith('asas-lims-pwa-') && key !== CACHE_NAME; }).map(function(key) { return caches.delete(key); }));
  }).then(function() { return self.clients.claim(); }));
});
self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);
  const scope = new URL(self.registration.scope);
  if (event.request.method !== 'GET' || url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  const relative = url.pathname.slice(scope.pathname.length);
  // Never cache API responses, authentication, attachments or the 44 MB PDF.
  if (!['','index.html','style.css','app-password.js','branch-map.js','i18n.js','runtime-config.js','asas_tests_module.js','manifest.webmanifest','logo.jpg'].includes(relative)) return;
  event.respondWith((async function() {
    const cache = await caches.open(CACHE_NAME);
    try {
      const response = await fetch(event.request);
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      if (event.request.mode === 'navigate') {
        const page = await cache.match('./index.html');
        if (page) return page;
      }
      return Response.error();
    }
  })());
});
