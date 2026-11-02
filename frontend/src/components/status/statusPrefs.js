/**
 * Default audience for new statuses (WhatsApp "Status privacy").
 * The server snapshots the audience on every status it stores, and enforces
 * it on read; this preference only decides what new statuses use.
 */
const key = (userId) => `whatsup_status_privacy_${userId}`;

export function getStatusPrivacy(userId) {
  try {
    const value = JSON.parse(localStorage.getItem(key(userId)) || "null");
    if (value && ["CONTACTS", "CONTACTS_EXCEPT", "ONLY_SHARE_WITH", "EVERYONE"].includes(value.visibility)) {
      return { visibility: value.visibility, users: Array.isArray(value.users) ? value.users.map(Number) : [] };
    }
  } catch {
    /* ignore */
  }
  return { visibility: "CONTACTS", users: [] };
}

export function setStatusPrivacy(userId, value) {
  try {
    localStorage.setItem(key(userId), JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export const STATUS_COLORS = ["#075E54", "#128C7E", "#1D5C4C", "#2A3942", "#5B2A86", "#9C27B0", "#C2185B", "#D35400", "#B7950B", "#1F618D", "#2E4053", "#0B5345"];
