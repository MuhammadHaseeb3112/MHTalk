import { getState } from "../../store/store";
import { sortedGroup } from "./statusRing";

/*
 * WhatsApp-style avatar actions that can be triggered from anywhere
 * (chat list, chat header, contact info):
 *   - a ringed avatar opens that person's status
 *   - a chat-list avatar without status opens the profile pop-up card
 *   - the chat-header avatar with status asks "View profile picture / View status"
 */
let overlay = null;
const listeners = new Set();
export function setOverlay(next) {
  overlay = next;
  listeners.forEach((listener) => listener());
}
export const subscribeOverlay = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function openUserStatus(userId) {
  const group = getState().statusFeed.find((item) => Number(item.user?.id) === Number(userId));
  if (group?.statuses?.length) setOverlay({ type: "status", group: sortedGroup(group) });
  return Boolean(group?.statuses?.length);
}

export function openProfilePeek(room, title, photo) {
  setOverlay({ type: "peek", room, title, photo });
}

export function openAvatarMenu(anchor, { userId, title, photo, onInfo }) {
  setOverlay({ type: "menu", anchor, userId, title, photo, onInfo });
}

export function openPhoto(title, photo) {
  setOverlay({ type: "photo", title, photo });
}

export const getOverlay = () => overlay;
