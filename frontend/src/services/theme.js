/**
 * Light / dark theme (Settings → Chats → Theme).
 *
 * The choice ("system" | "light" | "dark") is stored per browser. The tiny
 * inline script in index.html applies it before React renders (no flash);
 * this module keeps it in sync afterwards, follows the OS setting live when
 * "System default" is chosen, and updates the browser/PWA theme-color.
 */

export const THEME_KEY = "whatsup_theme";
export const THEME_OPTIONS = [
  { value: "system", label: "System default" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];
// Match the header / status-bar colour of each theme.
const THEME_COLORS = { light: "#f0f2f5", dark: "#161717" };

const media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
const listeners = new Set();

export function getThemePref() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return THEME_OPTIONS.some((option) => option.value === value) ? value : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(pref = getThemePref()) {
  if (pref === "light" || pref === "dark") return pref;
  return media?.matches ? "light" : "dark";
}

export function applyTheme(pref = getThemePref()) {
  const theme = resolveTheme(pref);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => meta.setAttribute("content", THEME_COLORS[theme]));
  listeners.forEach((listener) => listener(theme, pref));
  return theme;
}

export function setThemePref(pref) {
  try {
    localStorage.setItem(THEME_KEY, pref);
  } catch {
    /* private mode: still apply for this session */
  }
  return applyTheme(pref);
}

export function subscribeTheme(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Call once at startup: follow the OS live and other tabs' choices. */
export function initTheme() {
  applyTheme();
  media?.addEventListener?.("change", () => {
    if (getThemePref() === "system") applyTheme("system");
  });
  window.addEventListener("storage", (event) => {
    if (event.key === THEME_KEY) applyTheme();
  });
}
