import axios from "axios";

/**
 * Central HTTP client.
 *
 * - Base URL defaults to the Vite proxy (`/api/`); set VITE_API_URL to call a
 *   backend on another origin (for example http://localhost:8001/api/).
 * - Attaches the JWT access token to every request.
 * - On a 401 it refreshes the access token once (sharing a single refresh
 *   request between concurrent calls) and retries the original request.
 *   If refreshing fails the session is cleared and listeners are notified.
 */

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export const API_BASE = import.meta.env.VITE_API_URL || "/api/";

export const tokens = {
  get access() {
    try { return localStorage.getItem(ACCESS_KEY) || ""; } catch { return ""; }
  },
  get refresh() {
    try { return localStorage.getItem(REFRESH_KEY) || ""; } catch { return ""; }
  },
  set({ access, refresh }) {
    try {
      if (access) localStorage.setItem(ACCESS_KEY, access);
      if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    } catch { /* storage unavailable (private mode) */ }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    } catch { /* storage unavailable */ }
  },
};

const sessionListeners = new Set();
/** Subscribe to "session expired" events. Returns an unsubscribe function. */
export function onSessionExpired(listener) {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const access = tokens.access;
  if (access && !config.skipAuth) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

let refreshPromise = null;

/** Refresh the access token. Concurrent callers share one network request. */
export function refreshAccessToken() {
  if (!tokens.refresh) return Promise.reject(new Error("No refresh token"));
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${API_BASE.replace(/\/$/, "")}/accounts/token/refresh/`, { refresh: tokens.refresh })
      .then((response) => {
        tokens.set({ access: response.data.access, refresh: response.data.refresh });
        return response.data.access;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;
    const isAuthCall = /accounts\/(login|register|token\/refresh)\//.test(original.url || "");
    if (status === 401 && !original._retried && !isAuthCall && tokens.refresh) {
      original._retried = true;
      try {
        const access = await refreshAccessToken();
        original.headers = { ...(original.headers || {}), Authorization: `Bearer ${access}` };
        return api(original);
      } catch {
        tokens.clear();
        sessionListeners.forEach((listener) => listener());
      }
    } else if (status === 401 && !isAuthCall) {
      tokens.clear();
      sessionListeners.forEach((listener) => listener());
    }
    return Promise.reject(error);
  },
);

/** Turn any API error into one readable sentence for the UI. */
export function errorMessage(error, fallback = "Something went wrong. Please try again.") {
  const data = error?.response?.data;
  if (typeof data === "string" && data.length < 300 && !data.trim().startsWith("<")) return data;
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.error === "string") return data.error;
  if (typeof data?.message === "string" && error?.response?.status >= 400) return data.message;
  if (data && typeof data === "object") {
    const parts = Object.entries(data).map(([field, value]) => {
      const text = Array.isArray(value) ? value.map(String).join(" ") : typeof value === "object" ? JSON.stringify(value) : String(value);
      return field === "non_field_errors" || field === "detail" ? text : `${field.replace(/_/g, " ")}: ${text}`;
    });
    if (parts.length) return parts.join(" ");
  }
  const code = error?.response?.status;
  if (code === 502 || code === 503 || code === 504) return "The server isn't reachable right now (it may be restarting). Please try again.";
  if (code >= 500) return `Server error (${code}). Please try again.`;
  if (code === 413) return "This file is too large to upload.";
  if (error?.response?.status === 403) return "You don't have permission to do that.";
  if (!error?.response) return "Can't reach the server. Check your connection.";
  return fallback;
}

/** Normalise list endpoints that may return arrays or paginated envelopes. */
export function asList(data) {
  if (Array.isArray(data)) return data;
  for (const key of ["results", "data", "items"]) {
    if (Array.isArray(data?.[key])) return data[key];
  }
  return [];
}

/** Absolute URL for media paths such as /media/chat/x.jpg. */
export function mediaUrl(path) {
  if (!path || typeof path !== "string") return "";
  if (/^(https?:|data:|blob:)/i.test(path)) return path;
  try {
    const base = new URL(API_BASE, window.location.origin);
    return `${base.origin}${path.startsWith("/") ? path : `/${path}`}`;
  } catch {
    return path;
  }
}

/** WebSocket URL for a path such as /ws/chat/inbox/. */
export function socketUrl(path) {
  const configured = import.meta.env.VITE_WS_URL;
  let origin;
  if (configured) {
    origin = configured.replace(/\/$/, "");
  } else {
    const base = new URL(API_BASE, window.location.origin);
    origin = `${base.protocol === "https:" ? "wss:" : "ws:"}//${base.host}`;
  }
  return `${origin}${path}?token=${encodeURIComponent(tokens.access)}`;
}

export default api;
