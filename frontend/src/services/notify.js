/**
 * User-facing notification preferences: incoming-message sound, desktop
 * notifications and the tab title badge. Preferences are per-browser.
 */

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

let audioContext = null;
export function playIncomingSound() {
  if (!getNotificationPrefs().sound) return;
  try {
    audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
    const now = audioContext.currentTime;
    [880, 1320].forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, now + index * 0.09);
      gain.gain.exponentialRampToValueAtTime(0.08, now + index * 0.09 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.09 + 0.16);
      oscillator.connect(gain).connect(audioContext.destination);
      oscillator.start(now + index * 0.09);
      oscillator.stop(now + index * 0.09 + 0.18);
    });
  } catch {
    /* audio blocked until the user interacts with the page */
  }
}

export async function requestDesktopPermission() {
  if (!("Notification" in window)) return "unsupported";
  if (Notification.permission === "granted") return "granted";
  return Notification.requestPermission();
}

export function showDesktopNotification(title, body, onClick) {
  const prefs = getNotificationPrefs();
  if (!prefs.desktop || !("Notification" in window) || Notification.permission !== "granted") return;
  if (document.visibilityState === "visible" && document.hasFocus()) return;
  try {
    const notification = new Notification(title, {
      body: prefs.preview ? body : "New message",
      icon: "/pwa-192.png",
      tag: title,
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

export function setTitleBadge(count) {
  document.title = count > 0 ? `(${count}) MHTalk` : "MHTalk";
}
