/**
 * Global dialog host so any component can open a confirmation/choice
 * dialog without owning modal state (replaces window.confirm/prompt).
 */
let current = null;
const listeners = new Set();
const emit = () => listeners.forEach((listener) => listener(current));

/** Render `render(close)` inside the DialogHost. */
export function openDialog(render) {
  const close = () => {
    current = null;
    emit();
  };
  current = { render, close, key: Date.now() };
  emit();
  return close;
}

export function subscribeDialogs(listener) {
  listeners.add(listener);
  listener(current);
  return () => listeners.delete(listener);
}
