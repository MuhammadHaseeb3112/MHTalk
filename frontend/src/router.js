import { useSyncExternalStore } from "react";

/**
 * Tiny History-API router (/, /login, /signup). Avoids an extra dependency
 * for three routes while still giving real, shareable URLs.
 */
const listeners = new Set();
const notify = () => listeners.forEach((listener) => listener());
window.addEventListener("popstate", notify);

export function navigate(path, { replace = false } = {}) {
  if (window.location.pathname === path) return;
  if (replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  notify();
}

export function usePathname() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => window.location.pathname.replace(/\/+$/, "") || "/",
  );
}
