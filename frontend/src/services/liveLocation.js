/**
 * Live location sharing (like WhatsApp's 15 min / 1 hour / 8 hours).
 *
 * While a share is active this tab watches the GPS and sends the new
 * position to the server (at most every 10 s, or sooner after a big move).
 * Active shares are kept in localStorage so they resume after a reload.
 */
import { messageApi } from "../api/endpoints";

const KEY = "mhtalk.liveLocations";
const MIN_INTERVAL = 10000;
const shares = new Map(); // messageId -> { roomId, until, watchId, lastSent, timer }
const listeners = new Set();

function load() {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function persist() {
  try {
    const list = [...shares.entries()].map(([id, share]) => ({ id, roomId: share.roomId, until: share.until }));
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable: sharing still works until reload */
  }
}

function emit() {
  listeners.forEach((listener) => listener());
}

export function subscribeLiveLocation(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isSharingLive(messageId) {
  return shares.has(Number(messageId));
}

function track(messageId, roomId, until) {
  const id = Number(messageId);
  if (shares.has(id) || !navigator.geolocation || until <= Date.now()) return;
  const share = { roomId, until, watchId: null, lastSent: 0, timer: null };
  shares.set(id, share);
  share.watchId = navigator.geolocation.watchPosition(
    (position) => {
      const now = Date.now();
      if (now >= share.until) {
        stopLiveLocation(id, { notify: false });
        return;
      }
      if (now - share.lastSent < MIN_INTERVAL) return;
      share.lastSent = now;
      const { latitude, longitude, accuracy } = position.coords;
      messageApi
        .liveLocation(id, { latitude, longitude, accuracy: Number.isFinite(accuracy) ? Math.round(accuracy) : undefined })
        .catch(() => stopLiveLocation(id, { notify: false }));
    },
    () => {},
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 30000 },
  );
  share.timer = window.setTimeout(() => stopLiveLocation(id, { notify: false }), until - Date.now());
  persist();
  emit();
}

export function startLiveLocation(roomId, message) {
  const until = Date.parse(message?.content?.live_until || "");
  if (!message?.id || !Number.isFinite(until)) return;
  track(message.id, roomId, until);
}

export async function stopLiveLocation(messageId, { notify = true } = {}) {
  const id = Number(messageId);
  const share = shares.get(id);
  if (share) {
    if (share.watchId !== null) navigator.geolocation.clearWatch(share.watchId);
    window.clearTimeout(share.timer);
    shares.delete(id);
    persist();
    emit();
  }
  if (notify) {
    try {
      await messageApi.liveLocation(id, { stop: true });
    } catch {
      /* already ended */
    }
  }
}

/** Resume shares started before a reload (called once after login). */
export function resumeLiveLocations() {
  load().forEach((item) => {
    if (item.until > Date.now()) track(item.id, item.roomId, item.until);
  });
  persist();
}
