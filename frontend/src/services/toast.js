/** Global toast notifications (no browser alert()). */

let toasts = [];
const listeners = new Set();
let counter = 0;

function emit() {
  listeners.forEach((listener) => listener(toasts));
}

export function toast(message, { type = "info", duration = 3500, action } = {}) {
  if (!message) return null;
  const id = ++counter;
  toasts = [...toasts.filter((item) => item.message !== message), { id, message, type, action }].slice(-4);
  emit();
  if (duration) window.setTimeout(() => dismissToast(id), duration);
  return id;
}

toast.error = (message, options) => toast(message, { type: "error", duration: 5000, ...options });
toast.success = (message, options) => toast(message, { type: "success", ...options });

export function dismissToast(id) {
  toasts = toasts.filter((item) => item.id !== id);
  emit();
}

export function subscribeToasts(listener) {
  listeners.add(listener);
  listener(toasts);
  return () => listeners.delete(listener);
}
