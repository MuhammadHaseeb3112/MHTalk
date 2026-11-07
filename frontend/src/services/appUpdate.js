/**
 * "App update" in Settings: knows whether a newer MHTalk is ready, what it
 * changes (release notes from the server) and installs it when the user
 * says so. The app never updates itself behind the user's back.
 */
import { useSyncExternalStore } from "react";
import NOTES from "../releaseNotes.json";

export const RELEASES = NOTES;
export const APP_VERSION = NOTES[0]?.version || "1.0.0";

let state = { available: false, latest: null, releases: NOTES, waiting: null, checking: false, prompt: false };
let promptTimer = null;
let openRequested = false;
const listeners = new Set();

function set(patch) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

function newer(a, b) {
  const pa = String(a).split(".").map(Number);
  const pb = String(b).split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0);
  }
  return false;
}

export function useAppUpdate() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
  );
}

/** Ask the server which version is live (never from the offline cache). */
export async function checkForUpdate() {
  set({ checking: true });
  try {
    const response = await fetch(`/release-notes.json?t=${Date.now()}`, { cache: "no-store" });
    const releases = response.ok ? await response.json() : null;
    if (Array.isArray(releases) && releases.length) {
      const latest = releases[0];
      const isNewer = newer(latest.version, APP_VERSION);
      set({ releases, latest: isNewer ? latest : null, available: isNewer || Boolean(state.waiting) });
      if (isNewer) showUpdatePrompt(latest.version);
    }
  } catch {
    /* offline: try again later */
  } finally {
    set({ checking: false });
  }
  return state.available;
}

/** The service worker has the new files downloaded and is waiting. */
export function setWaitingWorker(worker) {
  set({ waiting: worker, available: true });
  showUpdatePrompt("waiting");
  checkForUpdate();
}

/**
 * The small "Update available" card: shown once per new version, hides
 * itself after 12 seconds or on "Later" (Settings keeps the green dot).
 */
export function showUpdatePrompt(key) {
  try {
    if (sessionStorage.getItem("mhtalk_update_prompted") === String(key)) return;
    sessionStorage.setItem("mhtalk_update_prompted", String(key));
  } catch {
    /* private mode */
  }
  window.clearTimeout(promptTimer);
  set({ prompt: true });
  promptTimer = window.setTimeout(() => set({ prompt: false }), 12000);
}

export function hideUpdatePrompt() {
  window.clearTimeout(promptTimer);
  set({ prompt: false });
}

let reloadHook = null;
export function onApplyReload(fn) {
  reloadHook = fn;
}

/** Install the new version: switch to the waiting files and reload. */
export async function applyUpdate() {
  if (state.waiting) {
    reloadHook?.();
    state.waiting.postMessage({ type: "SKIP_WAITING" });
    // Fallback if the page doesn't reload on its own.
    window.setTimeout(() => window.location.reload(), 4000);
    return;
  }
  try {
    const keys = (await window.caches?.keys?.()) || [];
    await Promise.all(keys.map((key) => window.caches.delete(key)));
    const registrations = (await navigator.serviceWorker?.getRegistrations?.()) || [];
    await Promise.all(registrations.map((registration) => registration.update().catch(() => {})));
  } catch {
    /* nothing cached */
  }
  window.location.reload();
}

/** Open Settings → App update (from the "new version" toast). */
export function requestOpenUpdate() {
  openRequested = true;
  window.dispatchEvent(new CustomEvent("mhtalk:open-update"));
}
export function takeOpenUpdate() {
  const value = openRequested;
  openRequested = false;
  return value;
}

if (typeof window !== "undefined" && import.meta.env.PROD) {
  window.setTimeout(checkForUpdate, 8000);
  window.setInterval(checkForUpdate, 30 * 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkForUpdate();
  });
}
