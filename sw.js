'use strict';
const CACHE_NAME = 'techno-lims-pwa-10-9-0-system-review';
const APP_SHELL = [
  './','./index.html','./style.css?v=10-9-0-system-review','./app-password.js?v=10-9-0-system-review',
  './quality-management.js?v=10-9-0-system-review','./branch-map.js?v=10-9-0-system-review','./i18n.js?v=10-9-0-system-review',
  './runtime-config.js?v=10-9-0-system-review','./field-test-guide.html','./manifest.webmanifest',
  './techno-logo.svg','./engineering-pages-bg.jpg','./whatsapp-logo.svg','./telegram-logo.svg'
];
self.addEventListener('install', function(event) {
  event.waitUntil(caches.open(CACHE_NAME).then(function(cache) { return cache.addAll(APP_SHELL); }).then(function() { return self.skipWaiting(); }));
});
self.addEventListener('activate', function(event) {
  event.waitUntil(caches.keys().then(function(keys) {
    return Promise.all(keys.filter(function(key) { return key.startsWith('techno-lims-pwa-') && key !== CACHE_NAME; }).map(function(key) { return caches.delete(key); }));
  }).then(function() { return self.clients.claim(); }));
});
self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);
  const scope = new URL(self.registration.scope);
  if (event.request.method !== 'GET' || url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  const relative = url.pathname.slice(scope.pathname.length);
  const cacheable = ['','index.html','style.css','app-password.js','quality-management.js','branch-map.js','i18n.js','runtime-config.js','field-test-guide.html','manifest.webmanifest','techno-logo.svg','engineering-pages-bg.jpg','whatsapp-logo.svg','telegram-logo.svg'];
  if (!cacheable.includes(relative)) return;
  if (event.request.mode === 'navigate' && url.searchParams.has('release')) {
    event.respondWith((async function() {
      const keys = await caches.keys();
      await Promise.all(keys.filter(function(key) { return key.startsWith('techno-lims-pwa-'); }).map(function(key) { return caches.delete(key); }));
      return fetch(new Request(event.request,{cache:'reload'}));
    })());
    return;
  }
  event.respondWith((async function() {
    const cache = await caches.open(CACHE_NAME);
    try {
      const request = url.searchParams.has('v') ? new Request(event.request,{cache:'reload'}) : event.request;
      const response = await fetch(request);
      if (response.ok) await cache.put(event.request,response.clone());
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
