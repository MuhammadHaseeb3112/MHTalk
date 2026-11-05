/**
 * User-facing notification preferences: incoming-message sound, desktop
 * notifications and the tab title badge. Preferences are per-browser.
 */

import { playSound } from "./sounds";

const PREFS_KEY = "mhtalk_notification_prefs";

export function getNotificationPrefs() {
  try {
    return { sound: true, desktop: false, preview: true, enterToSend: true, backgroundPush: false, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { sound: true, desktop: false, preview: true, enterToSend: true, backgroundPush: false };
  }
}

export function setNotificationPrefs(patch) {
  const next = { ...getNotificationPrefs(), ...patch };
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  return next;
}

export function playIncomingSound() {
  if (!getNotificationPrefs().sound) return;
  playSound("message");
}

export async function requestDesktopPermission() {
  if (!("Notification" in window)) return "unsupported";
  if (Notification.permission === "granted") return "granted";
  return Notification.requestPermission();
}

export function showDesktopNotification(title, body, onClick, options = {}) {
  const prefs = getNotificationPrefs();
  if (!prefs.desktop || !("Notification" in window) || Notification.permission !== "granted") return;
  if (document.visibilityState === "visible" && document.hasFocus()) return;
  try {
    const notification = new Notification(title, {
      body: prefs.preview ? body : "New message",
      icon: "/pwa-192.png",
      tag: options.tag || title,
      requireInteraction: Boolean(options.requireInteraction),
      renotify: Boolean(options.tag),
    });
    notification.onclick = () => {
      window.focus();
      onClick?.();
      notification.close();
    };
  } catch {
    /* some browsers require a service worker */
  }
}

let baseTitle = "MHTalk";
let titleOverride = null;
export function setTitleBadge(count) {
  baseTitle = count > 0 ? `(${count}) MHTalk` : "MHTalk";
  if (!titleOverride) document.title = baseTitle;
}

/** A call shows in the tab title ("📞 Ayesha is calling…" blinks). Pass null to clear. */
let titleTimer = null;
export function setCallTitle(text, { blink = false } = {}) {
  window.clearInterval(titleTimer);
  titleTimer = null;
  titleOverride = text;
  if (!text) {
    document.title = baseTitle;
    return;
  }
  document.title = text;
  if (blink) {
    let on = true;
    titleTimer = window.setInterval(() => {
      on = !on;
      document.title = on ? text : baseTitle;
    }, 1000);
  }
}
