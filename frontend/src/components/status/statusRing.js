import { useStore } from "../../store/store";

/**
 * WhatsApp-style status ring for a user's avatar:
 * "new" (green) while they have statuses I haven't seen, "seen" (grey)
 * once I've viewed them all, undefined when they have none.
 */
export function useStatusGroup(userId) {
  return useStore((state) => (userId ? state.statusFeed.find((group) => Number(group.user?.id) === Number(userId)) || null : null));
}

export function ringFor(group) {
  if (!group?.statuses?.length) return undefined;
  return Number(group.unseen_count) > 0 ? "new" : "seen";
}

export function sortedGroup(group) {
  return { ...group, statuses: [...group.statuses].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)) };
}
