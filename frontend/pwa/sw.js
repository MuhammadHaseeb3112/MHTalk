/*
 * MHTalk service worker (hand-written; generated into dist/sw.js at build
 * time by pwa/vite-plugin.js, which fills in the version and file list).
 *
 * - Precaches the built app shell (index.html, JS, CSS, icons) in a cache
 *   named after the build, so the app starts instantly and old builds are
 *   dropped on activate.
 * - Never touches /api, /ws, /media, /admin, /static or other origins.
 * - Offline navigations get offline.html.
 * - A new build waits until the page asks it to take over ("New version
 *   available — Reload" toast posts SKIP_WAITING).
 * - Web Push: shows message / call notifications and deep-links on click.
 * - Share target: files shared to the installed app ("Share → MHTalk", also
 *   Gboard's GIF/sticker fallback) are parked in a cache and the app opens
 *   "Send to…" (see ShareReceiver.jsx).
 */

const VERSION = "__MHTALK_SW_VERSION__";
const PRECACHE = [/* __MHTALK_SW_PRECACHE__ */];
const CACHE_PREFIX = "mhtalk-shell-";
const CACHE = CACHE_PREFIX + VERSION;
const SHELL_URL = "/index.html";
const OFFLINE_URL = "/offline.html";
const BYPASS = /^\/(api|ws|media|admin|static)(\/|$)|^\/release-notes\.json$/;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll(PRECACHE.map((url) => new Request(url, { cache: "reload" }))),
    ),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE).map((key) => caches.delete(key)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "GET_VERSION") event.source?.postMessage({ type: "VERSION", version: VERSION });
});

const SHARE_CACHE = "mhtalk-share";

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method === "POST" && url.origin === self.location.origin && url.pathname === "/share-target") {
    event.respondWith(handleShare(request));
    return;
  }
  if (request.method !== "GET") return;
  if (url.origin !== self.location.origin || BYPASS.test(url.pathname)) return;
  if (request.headers.get("range")) return;

  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
    return;
  }
  event.respondWith(handleAsset(request));
});

async function handleShare(request) {
  try {
    const form = await request.formData();
    const cache = await caches.open(SHARE_CACHE);
    for (const key of await cache.keys()) await cache.delete(key);
    const files = form.getAll("media").filter((item) => item && typeof item === "object" && item.size);
    const meta = {
      at: Date.now(),
      title: String(form.get("title") || ""),
      text: String(form.get("text") || ""),
      url: String(form.get("url") || ""),
      files: files.map((file, index) => ({ key: `/__share/${index}`, name: file.name || `shared-${index}`, type: file.type || "" })),
    };
    await Promise.all(
      files.map((file, index) =>
        cache.put(`/__share/${index}`, new Response(file, { headers: { "content-type": file.type || "application/octet-stream" } })),
      ),
    );
    await cache.put("/__share/meta", new Response(JSON.stringify(meta), { headers: { "content-type": "application/json" } }));
  } catch {
    /* nothing to share */
  }
  return Response.redirect("/?share=1", 303);
}

async function handleNavigation(request) {
  const cache = await caches.open(CACHE);
  // Offline: show the friendly page instead of a half-working app.
  if (self.navigator && self.navigator.onLine === false) {
    return (await cache.match(OFFLINE_URL)) || Response.error();
  }
  // Fast start: the shell of this build, straight from the cache.
  const shell = await cache.match(SHELL_URL);
  if (shell) return shell;
  try {
    return await fetch(request);
  } catch {
    return (await cache.match(OFFLINE_URL)) || Response.error();
  }
}

async function handleAsset(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request, { ignoreSearch: false });
  if (cached) return cached;
  const response = await fetch(request);
  // Keep same-origin static files of this build (e.g. lazily loaded chunks).
  if (response.ok && response.type === "basic" && new URL(request.url).pathname.startsWith("/assets/")) {
    cache.put(request, response.clone());
  }
  return response;
}

/* ------------------------------------------------------------------ push */

self.addEventListener("push", (event) => {
  let data;
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(showPush(data));
});

async function showPush(data) {
  // A missed-call card replaces the "Incoming call" notification.
  if (data.call_id && data.type === "message") {
    const ringing = await self.registration.getNotifications({ tag: `call-${data.call_id}` });
    ringing.forEach((notification) => notification.close());
  }
  const isCall = data.type === "call";
  return self.registration.showNotification(data.title || "MHTalk", {
    body: data.body || "New message",
    icon: data.icon || "/pwa-192.png",
    badge: data.badge || "/pwa-badge-96.png",
    tag: data.tag || (data.room_id ? `room-${data.room_id}` : "mhtalk"),
    renotify: true,
    requireInteraction: Boolean(data.require_interaction),
    vibrate: isCall ? [400, 200, 400, 200, 400] : [120, 60, 120],
    timestamp: Date.now(),
    data: { url: data.url || "/", room_id: data.room_id || null, type: data.type || "message" },
  });
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const { url = "/", room_id: roomId } = event.notification.data || {};
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const client = windows.find((item) => new URL(item.url).origin === self.location.origin);
      if (client) {
        await client.focus();
        if (roomId) client.postMessage({ type: "open-room", room_id: roomId });
        return;
      }
      await self.clients.openWindow(new URL(url, self.location.origin).href);
    })(),
  );
});
