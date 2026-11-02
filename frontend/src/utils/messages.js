import { formatPhone } from "./phone";
/**
 * Domain helpers: room normalisation, display names (saved contact name wins),
 * message previews, special message payloads (call cards, status reactions)
 * and attachment classification.
 */

export const CALL_PREFIX = "__MHTALK_CALL_EVENT__:";
export const STATUS_REACTION_PREFIX = "__MHTALK_STATUS_REACTION__:";
/** Chat notices such as "You turned on disappearing messages." */
export const SYSTEM_PREFIX = "__MHTALK_SYSTEM__:";
export const GROUP_EVENT_PREFIX = "__MHTALK_GROUP_EVENT__:";

export function parseSpecial(content) {
  if (typeof content !== "string" || !content.includes("__MHTALK_")) return null;
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start < 0 || end < start) return null;
  try {
    const payload = JSON.parse(content.slice(start, end + 1));
    if (payload?.kind === "call_event" || payload?.kind === "status_reaction" || payload?.kind === "disappearing" || payload?.kind === "group_event") return payload;
  } catch {
    /* not a special payload */
  }
  return null;
}

export function callSummary(event, myId) {
  const video = String(event.call_type).toUpperCase() === "VIDEO";
  const outgoing = Number(event.caller_id) === Number(myId);
  if (event.is_group) {
    // One card for the whole group: "joined" vs "missed" depends on the viewer.
    const kind = video ? "video" : "voice";
    const count = Number(event.joined_count) || 0;
    const joined = outgoing || (event.joined_ids || []).some((id) => Number(id) === Number(myId));
    const declined = (event.declined_ids || []).some((id) => Number(id) === Number(myId));
    const answered = joined && count > 1;
    let label;
    if (answered) label = `Group ${kind} call · ${count} joined`;
    else if (joined) label = `Group ${kind} call · No answer`;
    else label = declined ? `Declined group ${kind} call` : `Missed group ${kind} call`;
    return { video, outgoing, answered, label, missed: !joined && !declined, group: true, joinedCount: count };
  }
  const answered = Boolean(event.answered_at);
  let label;
  if (answered) label = video ? "Video call" : "Voice call";
  else if (outgoing) label = String(event.status).toUpperCase() === "REJECTED" ? "Call declined" : "No answer";
  else label = video ? "Missed video call" : "Missed voice call";
  return { video, outgoing, answered, label, missed: !answered && !outgoing };
}

export function attachmentKind(attachment) {
  const mime = String(attachment?.mime_type || "").toLowerCase();
  const name = String(attachment?.file_name || attachment?.file || "").toLowerCase();
  if (mime.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|heic)$/.test(name)) return "image";
  if (mime.startsWith("video/") || /\.(mp4|webm|mov|m4v|mkv)$/.test(name)) return "video";
  if (mime.startsWith("audio/") || /\.(mp3|wav|ogg|m4a|aac|opus|weba)$/.test(name)) return "audio";
  return "document";
}

export function messageKind(message) {
  if (!message) return "empty";
  if (message.is_deleted) return "deleted";
  if (message.voice_note?.audio) return "voice";
  const special = parseSpecial(message.content);
  if (special?.kind === "call_event") return "call";
  if (special?.kind === "status_reaction") return "status_reaction";
  if (special?.kind === "group_event") return "group_event";
  if (special?.kind === "disappearing") return "system";
  if (message.is_view_once) return "view_once";
  if (message.message_type === "POLL") return "poll";
  const first = message.attachments?.[0];
  if (first) return attachmentKind(first);
  if (message.message_type === "CONTACT") return "contact";
  if (message.message_type === "LOCATION") return "location";
  return "text";
}

/** True for chat notices that render as a centred pill, not a bubble. */
export function isSystemMessage(message) {
  return messageKind(message) === "system";
}

export const DISAPPEARING_OPTIONS = [
  { seconds: 86400, label: "24 hours" },
  { seconds: 604800, label: "7 days" },
  { seconds: 7776000, label: "90 days" },
  { seconds: 0, label: "Off" },
];

export function disappearingLabel(seconds) {
  return DISAPPEARING_OPTIONS.find((option) => option.seconds === Number(seconds || 0))?.label || "Off";
}

/** "You turned on disappearing messages. New messages will disappear…" */
export function systemText(message, myId, nameOf) {
  const payload = parseSpecial(message?.content);
  if (payload?.kind !== "disappearing") return "";
  const mine = Number(payload.actor_id ?? message.sender?.id) === Number(myId);
  const sender = message.sender;
  const who = mine
    ? "You"
    : nameOf
      ? nameOf(payload.actor_id ?? sender?.id)
      : sender?.profile?.display_name || formatPhone(sender?.phone_number) || "Someone";
  if (!Number(payload.seconds)) return `${who} turned off disappearing messages.`;
  return `${who} turned on disappearing messages. New messages will disappear from this chat ${disappearingLabel(payload.seconds)} after they're sent.`;
}

/** Is this view once media used up for me? (sender: opened by someone) */
export function viewOnceState(message, myId) {
  const opened = (message?.view_once_opened_by || []).map(Number);
  const mine = Number(message?.sender?.id) === Number(myId);
  const video = String(message?.attachments?.[0]?.mime_type || "").startsWith("video/") || message?.message_type === "VIDEO";
  const voice = message?.message_type === "VOICE";
  return { mine, video, voice, opened: mine ? opened.length > 0 : opened.includes(Number(myId)) };
}

/** Poll answer ids chosen by ``userId``. */
export function myPollVotes(poll, userId) {
  return (poll?.options || []).filter((option) => (option.voters || []).map(Number).includes(Number(userId))).map((option) => option.id);
}

/** Mentioned users present in ``message.mentions`` as {id, token} ("@<phone>"). */
export function mentionTokens(message, participants) {
  const ids = (message?.mentions || []).map(Number);
  if (!ids.length) return [];
  return ids
    .map((id) => {
      const user = (participants || []).find((p) => Number(p.user?.id) === id)?.user;
      return user?.phone_number ? { id, token: `@${user.phone_number}`, user } : null;
    })
    .filter(Boolean);
}

/** True for group system messages ("Alice joined using this group's invite link"). */
export function isGroupEvent(message) {
  return messageKind(message) === "group_event";
}

/**
 * Text of a group system message. The server stores "{actor} …"; WhatsApp
 * shows "You …" for your own actions and the saved/profile name otherwise.
 */
export function groupEventText(message, myId, nameOf) {
  const event = parseSpecial(message?.content);
  if (!event) return "";
  const actorId = Number(event.actor_id);
  let actor;
  if (actorId === Number(myId)) actor = "You";
  else actor = (nameOf && nameOf(actorId)) || event.actor_name || "Someone";
  // Former members / deleted accounts: use the name stored with the event.
  if (actor === "Unknown" || actor === "Deleted account") actor = event.actor_name || actor;
  return String(event.text || "").replace("{actor}", actor);
}

/** Text shown in the chat list / reply quote for a message. */
export function previewText(message, myId, nameOf) {
  const kind = messageKind(message);
  switch (kind) {
    case "group_event":
      return groupEventText(message, myId, nameOf);
    case "deleted":
      return Number(message.sender?.id) === Number(myId) ? "You deleted this message" : "This message was deleted";
    case "voice":
      return `Voice message${message.voice_note?.duration ? ` (${formatSeconds(message.voice_note.duration)})` : ""}`;
    case "call":
      return callSummary(parseSpecial(message.content), myId).label;
    case "status_reaction": {
      const payload = parseSpecial(message.content);
      return `Reacted ${payload.emoji} to a status`;
    }
    case "image":
      return message.content || "Photo";
    case "video":
      return message.content || "Video";
    case "audio":
      return message.attachments[0]?.file_name || "Audio";
    case "document":
      return message.attachments[0]?.file_name || "Document";
    case "contact":
      return `Contact: ${message.content?.name || ""}`.trim();
    case "location":
      return message.content?.name ? `📍 ${message.content.name}` : "📍 Location";
    case "poll":
      return `📊 Poll: ${message.poll?.question || message.content || ""}`.trim();
    case "view_once": {
      const { video, voice } = viewOnceState(message, myId);
      return voice ? "🎤 Voice message" : video ? "📹 Video" : "📷 Photo";
    }
    case "system":
      return systemText(message, myId, nameOf);
    default:
      return typeof message.content === "string" ? message.content : "";
  }
}

function formatSeconds(value) {
  const total = Math.max(0, Math.round(Number(value) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function userId(user) {
  return Number(user?.id ?? user);
}

/** Map saved contacts by contact user id for O(1) name lookups. */
export function contactsByUser(contacts) {
  const map = new Map();
  contacts.forEach((contact) => {
    const id = Number(contact?.contact_user?.id);
    if (id) map.set(id, contact);
  });
  return map;
}

/** WhatsApp naming: saved contact name > own profile name (shown as "~ name") > phone. */
export function displayUserName(user, contactMap, { me, fallback = "Unknown" } = {}) {
  if (!user) return fallback;
  if (me && Number(user.id) === Number(me.id)) return "You";
  const contact = contactMap?.get(Number(user.id));
  if (contact?.name?.trim()) return contact.name.trim();
  if (user.is_deleted) return "Deleted account";
  return formatPhone(user.phone_number) || user.profile?.display_name || fallback;
}

export function profileName(user) {
  const name = user?.profile?.display_name?.trim();
  return name && name !== user?.phone_number ? name : "";
}

export function isSavedContact(user, contactMap) {
  return Boolean(contactMap?.get(Number(user?.id)));
}

export function normalizeRoom(raw, myId) {
  const participants = Array.isArray(raw.participants) ? raw.participants : [];
  const isGroup = raw.room_type === "GROUP";
  const other = isGroup ? null : participants.find((p) => Number(p.user?.id) !== Number(myId))?.user || null;
  const last = raw.last_message || null;
  return {
    id: Number(raw.id),
    type: raw.room_type,
    isGroup,
    groupName: raw.name || "",
    description: raw.description || "",
    groupPhoto: raw.photo || null,
    participants,
    otherUser: other,
    createdById: raw.created_by_id ?? null,
    createdAt: raw.created_at,
    lastMessage: last,
    lastReaction: raw.last_reaction || null,
    activityAt: latestTime(last?.created_at, raw.last_reaction?.created_at) || raw.updated_at || raw.created_at,
    unread: Number(raw.unread_count || 0),
    isPinned: Boolean(raw.is_pinned),
    pinnedAt: raw.pinned_at || null,
    isFavorite: Boolean(raw.is_favorite),
    isArchived: Boolean(raw.is_archived),
    isMuted: Boolean(raw.is_muted),
    mutedUntil: raw.muted_until || null,
    disappearingSeconds: Number(raw.disappearing_seconds || 0),
    unreadMention: Boolean(raw.unread_mention),
    // Group permissions (true = only admins).
    editInfoAdminsOnly: raw.edit_info_admins_only !== false,
    sendAdminsOnly: Boolean(raw.send_messages_admins_only),
    addMembersAdminsOnly: raw.add_members_admins_only !== false,
  };
}

/** My participant row in a room (null when I'm not a member). */
export function myMembership(room, myId) {
  return room?.participants?.find((p) => Number(p.user?.id) === Number(myId)) || null;
}

/** Client mirrors of apps/chat/permissions.py (the server still enforces them). */
export function groupAbilities(room, myId) {
  const membership = myMembership(room, myId);
  const isAdmin = Boolean(membership?.is_admin);
  const isMember = Boolean(membership);
  return {
    isAdmin,
    isMember,
    canEditInfo: isMember && (isAdmin || !room.editInfoAdminsOnly),
    canSend: isMember && (isAdmin || !room.sendAdminsOnly),
    canAddMembers: isMember && (isAdmin || !room.addMembersAdminsOnly),
  };
}

export function roomTitle(room, contactMap, me) {
  if (!room) return "";
  if (room.isGroup) return room.groupName || "Group";
  if (!room.otherUser) return "Deleted account";
  return displayUserName(room.otherUser, contactMap, { me: null }) + (Number(room.otherUser.id) === Number(me?.id) ? " (You)" : "");
}

export function roomPhoto(room) {
  if (!room) return null;
  return room.isGroup ? room.groupPhoto : room.otherUser?.profile?.profile_picture || null;
}

export function sortRooms(rooms) {
  return rooms.sort((a, b) => {
    if (a.isPinned !== b.isPinned) return a.isPinned ? -1 : 1;
    if (a.isPinned && b.isPinned) return new Date(b.pinnedAt || 0) - new Date(a.pinnedAt || 0);
    return new Date(b.activityAt || 0) - new Date(a.activityAt || 0);
  });
}

export function newClientId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `c-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Group sender name colours live in tokens.css (--sender-0..9) so each theme
// can use shades that stay readable on its bubbles.
const SENDER_COLOR_COUNT = 10;
export function senderColor(id) {
  return `var(--sender-${Math.abs(Number(id) || 0) % SENDER_COLOR_COUNT})`;
}

export const URL_PATTERN = /(https?:\/\/[^\s<]+[^\s<.,:;"')\]])/gi;

/** Replace "@<phone>" mention tokens in ``text`` with "@Name" (chat list, quotes, notifications). */
export function readableMentions(text, message, participants, nameOfId) {
  let value = String(text ?? "");
  mentionTokens(message, participants).forEach(({ id, token }) => {
    value = value.split(token).join(`@${nameOfId(id)}`);
  });
  return value;
}

/* ---------------------------------------------------------------- Maps */

/** Slippy-map tile maths (OpenStreetMap, Web Mercator). */
export function osmTilePoint(latitude, longitude, zoom = 15) {
  const lat = Math.max(-85.0511, Math.min(85.0511, Number(latitude)));
  const scale = 2 ** zoom;
  const x = ((Number(longitude) + 180) / 360) * scale;
  const rad = (lat * Math.PI) / 180;
  const y = ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * scale;
  return { x, y, zoom };
}

export function googleMapsUrl(latitude, longitude) {
  return `https://www.google.com/maps/search/?api=1&query=${Number(latitude)},${Number(longitude)}`;
}

function latestTime(a, b) {
  if (!a) return b || null;
  if (!b) return a;
  return new Date(a) >= new Date(b) ? a : b;
}

/** The chat's newest reaction, if it is newer than its last message. */
export function activeReaction(room) {
  const reaction = room?.lastReaction;
  if (!reaction) return null;
  const last = room.lastMessage;
  if (last && new Date(last.created_at) >= new Date(reaction.created_at)) return null;
  return reaction;
}
