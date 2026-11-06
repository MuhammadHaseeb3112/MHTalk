/**
 * Installable app (PWA) glue:
 *   - registers /sw.js in production builds only (never in `vite` dev),
 *   - shows "New version available — Reload" when a new deploy is waiting,
 *   - turns service-worker notification clicks into "mhtalk:open-room",
 *   - keeps the browser's install prompt for Settings → "Install app".
 */
import { toast } from "./toast";
import { onApplyReload, requestOpenUpdate, setWaitingWorker } from "./appUpdate";

const installListeners = new Set();
let deferredPrompt = null;
let registrationPromise = null;
let reloading = false;

function emitInstall() {
  const state = getInstallState();
  installListeners.forEach((listener) => listener(state));
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // keep it for the Settings row instead of the mini-infobar
    deferredPrompt = event;
    emitInstall();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    emitInstall();
  });
}

export function isIos() {
  const ua = navigator.userAgent || "";
  return /iphone|ipad|ipod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function isStandalone() {
  return Boolean(window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone);
}

export function getInstallState() {
  return { installed: isStandalone(), canPrompt: Boolean(deferredPrompt), ios: isIos() };
}

export function subscribeInstall(listener) {
  installListeners.add(listener);
  return () => installListeners.delete(listener);
}

/** Show the browser's install dialog. Resolves to "accepted" | "dismissed" | "unavailable". */
export async function promptInstall() {
  if (!deferredPrompt) return "unavailable";
  const event = deferredPrompt;
  deferredPrompt = null;
  event.prompt();
  const choice = await event.userChoice.catch(() => ({ outcome: "dismissed" }));
  emitInstall();
  return choice?.outcome || "dismissed";
}

/** Service-worker registration (null in dev / unsupported browsers). */
export function getServiceWorkerRegistration() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return Promise.resolve(null);
  return registrationPromise || Promise.resolve(null);
}

function promptUpdate(worker) {
  // The user decides when to update: Settings shows a green dot and the
  // "App update" page explains what's new.
  setWaitingWorker(worker);
  onApplyReload(() => {
    reloading = true;
  });
  toast("A new version of MHTalk is ready", {
    duration: 8000,
    action: { label: "What's new", onClick: requestOpenUpdate },
  });
}

function watchForUpdates(registration) {
  if (registration.waiting && navigator.serviceWorker.controller) promptUpdate(registration.waiting);
  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;
    worker?.addEventListener("statechange", () => {
      // "installed" with an existing controller = an update is waiting.
      if (worker.state === "installed" && navigator.serviceWorker.controller) promptUpdate(worker);
    });
  });
  // Long-lived tabs / installed apps: look for new deploys now and then.
  const check = () => registration.update().catch(() => {});
  window.setInterval(check, 60 * 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") check();
  });
}

export function registerServiceWorker() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // Only reload when the user pressed "Reload" (not on the first install).
    if (!reloading) return;
    reloading = false;
    window.location.reload();
  });
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type === "open-room" && event.data.room_id) {
      window.dispatchEvent(new CustomEvent("mhtalk:open-room", { detail: Number(event.data.room_id) }));
    }
  });
  registrationPromise = new Promise((resolve) => {
    const register = () =>
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then((registration) => {
          watchForUpdates(registration);
          resolve(registration);
        })
        .catch(() => resolve(null));
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
  });
}

/** Room id from a notification deep link (/?room=12), removed from the URL. */
export function consumeLaunchRoom() {
  const params = new URLSearchParams(window.location.search);
  const room = Number(params.get("room"));
  if (!room) return null;
  params.delete("room");
  const query = params.toString();
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  return room;
}
