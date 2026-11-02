/**
 * "Go to message" requests (starred messages, search results, media, quotes).
 *
 * The target chat may not be open or loaded yet, so the request is kept until
 * that chat's message list has loaded and can scroll to it.
 */
const pending = new Map(); // roomId -> messageId

export function jumpToMessage(roomId, messageId) {
  if (!roomId || !messageId) return;
  pending.set(Number(roomId), Number(messageId));
  window.dispatchEvent(new CustomEvent("mhtalk:jump-pending", { detail: { roomId: Number(roomId) } }));
}

export function takePendingJump(roomId) {
  const id = pending.get(Number(roomId));
  pending.delete(Number(roomId));
  return id || null;
}
