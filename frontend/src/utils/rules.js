/** Client-side mirrors of the server's message rules (server still enforces them). */
export const EDIT_WINDOW_MS = 15 * 60 * 1000;
export const DELETE_WINDOW_MS = 48 * 60 * 60 * 1000;

export function canEdit(message, myId) {
  return Boolean(
    Number(message.sender?.id) === Number(myId) &&
      message.id &&
      !message.is_deleted &&
      (message.message_type === "TEXT" || !message.message_type) &&
      !message.attachments?.length &&
      !String(message.content || "").startsWith("__WHATSUP_") &&
      Date.now() - new Date(message.created_at).getTime() < EDIT_WINDOW_MS,
  );
}

export function canDeleteForEveryone(messages, myId) {
  return messages.every(
    (message) =>
      Number(message.sender?.id) === Number(myId) &&
      !message.is_deleted &&
      message.id &&
      !String(message.content || "").startsWith("__WHATSUP_GROUP_EVENT__") &&
      Date.now() - new Date(message.created_at).getTime() < DELETE_WINDOW_MS,
  );
}

/** Group contacts under their first letter (A–Z, then #). */
export function groupByLetter(contacts) {
  const groups = new Map();
  contacts.forEach((contact) => {
    const letter = /[a-z]/i.test(contact.name?.[0] || "") ? contact.name[0].toUpperCase() : "#";
    if (!groups.has(letter)) groups.set(letter, []);
    groups.get(letter).push(contact);
  });
  return [...groups.entries()].sort(([a], [b]) => (a === "#" ? 1 : b === "#" ? -1 : a.localeCompare(b)));
}
