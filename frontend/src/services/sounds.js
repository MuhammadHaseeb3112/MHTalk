/**
 * App sounds: the incoming-message chime, the incoming-call ringtone and the
 * outgoing "ring-ring" while the other side is ringing. Original sounds,
 * bundled by Vite (hashed under /assets/, so the service worker caches them).
 *
 * Browsers only allow audio after the person has interacted with the page
 * once (a click or a key press). Before that, play() is refused quietly.
 */
import messageUrl from "../assets/sounds/message.mp3";
import ringbackUrl from "../assets/sounds/ringback.mp3";
import ringtoneUrl from "../assets/sounds/ringtone.mp3";

const SOURCES = { message: messageUrl, ringtone: ringtoneUrl, ringback: ringbackUrl };
const VOLUME = { message: 0.6, ringtone: 0.9, ringback: 0.5 };
const cache = new Map();

function element(name) {
  if (!cache.has(name)) {
    const audio = new Audio(SOURCES[name]);
    audio.preload = "auto";
    audio.volume = VOLUME[name];
    cache.set(name, audio);
  }
  return cache.get(name);
}

/** Play a short sound once (overlapping plays are fine). */
export function playSound(name) {
  try {
    const audio = element(name).cloneNode();
    audio.volume = VOLUME[name];
    audio.play()?.catch(() => {});
  } catch {
    /* audio unavailable */
  }
}

/** Loop a sound until stop() is called. Returns { start, stop }. */
export function loopSound(name) {
  let audio = null;
  return {
    start() {
      try {
        audio = new Audio(SOURCES[name]);
        audio.loop = true;
        audio.volume = VOLUME[name];
        audio.play()?.catch(() => {});
      } catch {
        audio = null;
      }
    },
    stop() {
      if (!audio) return;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audio = null;
    },
  };
}

/** Load the files ahead of time, so the first ring starts instantly. */
export function preloadSounds() {
  Object.keys(SOURCES).forEach((name) => {
    try {
      element(name).load();
    } catch {
      /* ignore */
    }
  });
}
