import { useMemo } from "react";
import { useStore } from "../../store/store";
import { contactsByUser, displayUserName, previewText, readableMentions, roomTitle, sortRooms, activeReaction } from "../../utils/messages";
import { phoneDigits } from "../../utils/phone";

/** Typing label for a room ("typing…" / "Ali is typing…"). */
export function typingLabel(room, typingUsers, contactMap, me) {
  const ids = Object.keys(typingUsers || {}).map(Number).filter((id) => id !== Number(me?.id));
  if (!ids.length) return "";
  if (!room.isGroup) return "typing…";
  const names = ids
    .map((id) => room.participants.find((p) => Number(p.user?.id) === id)?.user)
    .filter(Boolean)
    .map((user) => displayUserName(user, contactMap).split(" ")[0]);
  if (names.length === 1) return `${names[0]} is typing…`;
  return `${names.length} people are typing…`;
}

export function matchesQuery(text, query) {
  return String(text || "").toLowerCase().includes(query);
}

/**
 * Build the visible chat list.
 * @param {"all"|"unread"|"favorites"|"groups"} filter
 * @param {boolean} archived  archived bucket instead of the main list
 */
export function useChatList({ filter = "all", archived = false, query = "" }) {
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const typing = useStore((state) => state.typing);
  const me = useStore((state) => state.me);
  const activeRoomId = useStore((state) => state.activeRoomId);

  return useMemo(() => {
    const contactMap = contactsByUser(contacts);
    const needle = query.trim().toLowerCase();
    const digits = phoneDigits(needle);
    const list = sortRooms(
      Object.values(rooms).filter((room) => {
        if (Boolean(room.isArchived) !== archived) return false;
        if (filter === "unread" && !(room.unread > 0 || room.id === activeRoomId)) return false;
        if (filter === "favorites" && !room.isFavorite) return false;
        if (filter === "groups" && !room.isGroup) return false;
        // Rooms with no history yet only show while open (like WhatsApp's empty new chat).
        if (!room.lastMessage && !room.isGroup && room.id !== activeRoomId) return false;
        return true;
      }),
    );

    const rows = list.map((room) => {
      const title = roomTitle(room, contactMap, me);
      const last = room.lastMessage;
      const senderName = room.isGroup && last?.sender ? displayUserName(last.sender, contactMap, { me }) : "";
      const nameOfId = (id) => {
        if (Number(id) === Number(me?.id)) return "You";
        const user = room.participants.find((p) => Number(p.user?.id) === Number(id))?.user;
        return user ? displayUserName(user, contactMap) : "Someone";
      };
      let preview = last ? readableMentions(previewText(last, me?.id, nameOfId), last, room.participants, nameOfId) : "";
      const reaction = activeReaction(room);
      if (reaction) {
        // WhatsApp: "Reacted 😂 to: "Voice message"" / "You reacted …" / "Bilal reacted …"
        const target = reaction.message ? previewText(reaction.message, me?.id, nameOfId) : "a message";
        const mine = Number(reaction.user_id) === Number(me?.id);
        const who = mine ? "You reacted" : room.isGroup ? `${nameOfId(reaction.user_id)} reacted` : "Reacted";
        preview = `${who} ${reaction.emoji} to: "${target}"`;
      }
      return {
        room,
        title,
        senderName,
        preview,
        reacted: Boolean(reaction),
        typingText: typingLabel(room, typing[room.id], contactMap, me),
      };
    });

    if (!needle) return rows;
    return rows.filter(({ room, title }) => {
      if (matchesQuery(title, needle)) return true;
      if (room.isGroup) return matchesQuery(room.groupName, needle);
      const user = room.otherUser;
      if (digits.length >= 3 && phoneDigits(user?.phone_number).includes(digits)) return true;
      if (matchesQuery(user?.profile?.display_name, needle)) return true;
      return matchesQuery(previewText(room.lastMessage, me?.id), needle);
    });
  }, [rooms, contacts, typing, me, activeRoomId, filter, archived, query]);
}
