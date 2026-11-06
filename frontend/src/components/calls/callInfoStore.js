/** Which call row is open in "Call info" (desktop shows it on the right). */
let selected = null; // { key, roomId, peerId }
const listeners = new Set();

export function selectCallInfo(next) {
  selected = next;
  listeners.forEach((listener) => listener());
}
export const subscribeCallInfo = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
export const getCallInfo = () => selected;
