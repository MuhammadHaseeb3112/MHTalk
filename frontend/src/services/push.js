/**
 * Background (Web Push) notifications: subscribe this browser so the server
 * can notify it when no MHTalk tab is open. Needs the production service
 * worker (see services/pwa.js) and VAPID keys on the server.
 */
import api from "../api/client";
import { getNotificationPrefs, setNotificationPrefs } from "./notify";
import { getServiceWorkerRegistration } from "./pwa";

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = window.atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function currentSubscription() {
  const registration = await getServiceWorkerRegistration();
  if (!registration?.pushManager) return { registration: null, subscription: null };
  return { registration, subscription: await registration.pushManager.getSubscription() };
}

async function sendToServer(subscription) {
  await api.post("notifications/push/subscribe/", {
    ...subscription.toJSON(),
    show_previews: getNotificationPrefs().preview,
  });
}

/**
 * Ask permission, subscribe and register with the server.
 * Throws an Error with a user-facing message when it cannot.
 */
export async function enableBackgroundPush() {
  if (!pushSupported()) throw new Error("This browser doesn't support background notifications.");
  const registration = await getServiceWorkerRegistration();
  if (!registration) throw new Error("Background notifications work in the installed / production app only.");
  const { data } = await api.get("notifications/push/public-key/");
  if (!data?.enabled || !data.public_key) throw new Error("Background notifications aren't set up on this server.");
  const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are blocked by your browser for this site.");
  await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  const key = urlBase64ToUint8Array(data.public_key);
  if (subscription) {
    // Re-subscribe if the server's key changed.
    const current = subscription.options?.applicationServerKey;
    const same = current && new Uint8Array(current).every((byte, index) => byte === key[index]);
    if (!same) {
      await subscription.unsubscribe().catch(() => {});
      subscription = null;
    }
  }
  if (!subscription) {
    try {
      // Some browsers hang when their push service is unreachable: give up after 20 s.
      subscription = await Promise.race([
        registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key }),
        new Promise((_, reject) => window.setTimeout(() => reject(new Error("timeout")), 20000)),
      ]);
    } catch {
      throw new Error("Couldn't turn on background notifications in this browser.");
    }
  }
  await sendToServer(subscription);
  setNotificationPrefs({ backgroundPush: true });
  return true;
}

/** Stop pushes to this browser (server + browser). */
export async function disableBackgroundPush({ keepPref = false } = {}) {
  if (!keepPref) setNotificationPrefs({ backgroundPush: false });
  const { subscription } = await currentSubscription().catch(() => ({ subscription: null }));
  if (!subscription) return;
  await api.post("notifications/push/unsubscribe/", { endpoint: subscription.endpoint }).catch(() => {});
  await subscription.unsubscribe().catch(() => {});
}

/**
 * At startup (after login): make sure the server knows this browser belongs
 * to the current account and has the latest "Show previews" choice.
 */
export async function syncBackgroundPush() {
  if (!getNotificationPrefs().backgroundPush || !pushSupported() || Notification.permission !== "granted") return;
  const { subscription } = await currentSubscription().catch(() => ({ subscription: null }));
  if (subscription) await sendToServer(subscription).catch(() => {});
}

/** Logging out: this device must stop receiving the account's pushes. */
export async function forgetBackgroundPushOnLogout() {
  const { subscription } = await currentSubscription().catch(() => ({ subscription: null }));
  if (!subscription) return;
  await api.post("notifications/push/unsubscribe/", { endpoint: subscription.endpoint }).catch(() => {});
}
