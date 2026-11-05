import { errorMessage } from "../api/client";
import { callApi, chatApi, contactsApi, messageApi, statusApi } from "../api/endpoints";
import { toast } from "../services/toast";
import { GIF_PREFIX, newClientId, normalizeRoom, attachmentKind, isGroupEvent, isSystemMessage, myPollVotes } from "../utils/messages";
import { dispatch, getState } from "./store";

/**
 * Application actions: every REST read/write the UI performs goes through
 * here so that the store stays consistent. Realtime events reuse the same
 * helpers (see services/realtime.js).
 */

const PAGE_SIZE = 60;
const myId = () => getState().me?.id;

/* ----------------------------------------------------------------------------
 * Loading
 * ------------------------------------------------------------------------- */

let roomsInFlight = null;
export function loadRooms() {
  if (roomsInFlight) return roomsInFlight;
  roomsInFlight = chatApi
    .rooms()
    .then((rows) => {
      const me = myId();
      const activeId = getState().activeRoomId;
      const rooms = rows.map((row) => {
        const room = normalizeRoom(row, me);
        return room.id === activeId && document.visibilityState === "visible" ? { ...room, unread: 0, unreadMention: false, _keepRead: true } : room;
      });
      // Keep the open conversation mounted even if it is no longer listed.
      const open = getState().rooms[activeId];
      if (open && !rooms.some((room) => room.id === activeId)) rooms.push({ ...open, _pinnedOpen: true });
      dispatch({ type: "rooms/set", rooms });
      return rooms;
    })
    .catch((error) => {
      if (error?.response?.status !== 401) toast.error(errorMessage(error, "Couldn't load your chats."));
      throw error;
    })
    .finally(() => {
      roomsInFlight = null;
    });
  return roomsInFlight;
}

let roomsTimer = null;
/** Coalesce bursts of "something changed" events into one list refresh. */
export function scheduleRoomsReload(delay = 250) {
  window.clearTimeout(roomsTimer);
  roomsTimer = window.setTimeout(() => loadRooms().catch(() => {}), delay);
}

export async function refreshRoom(roomId) {
  try {
    const raw = await chatApi.roomInfo(roomId);
    const previous = getState().rooms[roomId];
    const room = normalizeRoom(raw, myId());
    dispatch({
      type: "rooms/upsert",
      room: previous?._keepRead ? { ...room, unread: 0, unreadMention: false } : room,
    });
    return room;
  } catch (error) {
    if (error?.response?.status === 404) {
      // No longer a member (removed from group / left).
      dispatch({ type: "rooms/remove", roomId });
      if (getState().activeRoomId === roomId) dispatch({ type: "activeRoom", roomId: null });
    }
    return null;
  }
}

export async function loadContacts() {
  try {
    const contacts = await contactsApi.list();
    dispatch({ type: "contacts", contacts });
    return contacts;
  } catch {
    return getState().contacts;
  }
}

export async function loadBlocked() {
  try {
    const rows = await chatApi.blocked();
    dispatch({ type: "blocked", ids: rows.map((row) => Number(row.id)) });
  } catch {
    /* optional */
  }
}

export async function loadMessages(roomId) {
  dispatch({ type: "messages/loading", roomId });
  try {
    const items = await messageApi.list(roomId, { limit: PAGE_SIZE });
    dispatch({ type: "messages/set", roomId, items, hasMore: items.length >= PAGE_SIZE });
  } catch (error) {
    dispatch({ type: "messages/error", roomId, error: errorMessage(error, "Couldn't load messages.") });
  }
}

export async function loadOlderMessages(roomId) {
  const current = getState().messages[roomId];
  if (!current || current.loading || !current.hasMore) return;
  const oldest = current.items.find((item) => item.id);
  if (!oldest) return;
  dispatch({ type: "messages/loading", roomId });
  try {
    const items = await messageApi.list(roomId, { before: oldest.id, limit: PAGE_SIZE });
    dispatch({ type: "messages/prepend", roomId, items, hasMore: items.length >= PAGE_SIZE });
  } catch (error) {
    dispatch({ type: "messages/prepend", roomId, items: [], hasMore: true });
    toast.error(errorMessage(error));
  }
}

let statusTimer = null;
export async function loadStatus() {
  try {
    const [feed, mine] = await Promise.all([statusApi.feed(), statusApi.mine()]);
    dispatch({ type: "status/set", feed, mine });
  } catch {
    /* status is optional for the rest of the app */
  }
}
export function scheduleStatusReload() {
  window.clearTimeout(statusTimer);
  statusTimer = window.setTimeout(loadStatus, 300);
}

export async function loadCalls() {
  // Signed out (e.g. CallManager cleaning up while logging out): nothing to load.
  if (!getState().me) return;
  try {
    const [calls, missed, active] = await Promise.all([callApi.history(), callApi.missed(), callApi.active().catch(() => [])]);
    dispatch({ type: "calls/set", calls });
    dispatch({ type: "calls/missed", count: Number(missed?.unseen_count || 0) });
    dispatch({ type: "calls/active", byRoom: Object.fromEntries(active.map((item) => [item.room, item])) });
  } catch {
    /* optional */
  }
}

export async function acknowledgeMissedCalls() {
  if (!getState().missedUnseen) return;
  dispatch({ type: "calls/missed", count: 0 });
  try {
    await callApi.acknowledgeMissed();
  } catch {
    loadCalls();
  }
}

export async function bootstrap() {
  await Promise.allSettled([loadContacts(), loadRooms(), loadBlocked()]);
  loadStatus();
  loadCalls();
}

/* ----------------------------------------------------------------------------
 * Reading
 * ------------------------------------------------------------------------- */

const readTimers = {};
/** Mark a chat read on the server (debounced) and zero its badge locally. */
export function markRoomRead(roomId, { immediate = false } = {}) {
  const room = getState().rooms[roomId];
  if (room && (room.unread || room.unreadMention)) dispatch({ type: "rooms/patch", roomId, patch: { unread: 0, unreadMention: false } });
  window.clearTimeout(readTimers[roomId]);
  readTimers[roomId] = window.setTimeout(() => {
    chatApi.markRead(roomId).catch(() => {});
  }, immediate ? 0 : 400);
}

export function setActiveRoom(roomId) {
  const state = getState();
  const previous = state.activeRoomId;
  if (previous && previous !== roomId && state.rooms[previous]) {
    dispatch({ type: "rooms/patch", roomId: previous, patch: { _keepRead: false, _pinnedOpen: false } });
  }
  dispatch({ type: "activeRoom", roomId });
  if (roomId && state.rooms[roomId]) {
    dispatch({ type: "rooms/patch", roomId, patch: { _keepRead: true } });
  }
}

/* ----------------------------------------------------------------------------
 * Receiving (shared by inbox + room sockets)
 * ------------------------------------------------------------------------- */

const countedIncoming = new Set();
export function receiveMessage(roomId, message, { onNew } = {}) {
  const state = getState();
  const room = state.rooms[roomId];
  const isOwn = Number(message.sender?.id) === Number(state.me?.id);
  const key = `${roomId}:${message.id}`;
  const firstTime = !countedIncoming.has(key);
  countedIncoming.add(key);
  if (countedIncoming.size > 4000) {
    const keep = [...countedIncoming].slice(-2000);
    countedIncoming.clear();
    keep.forEach((item) => countedIncoming.add(item));
  }

  dispatch({ type: "messages/upsert", roomId, message });

  if (!room) {
    scheduleRoomsReload(0);
    if (firstTime && !isOwn) onNew?.(message, null);
    return;
  }

  const lastTime = new Date(room.lastMessage?.created_at || 0).getTime();
  const thisTime = new Date(message.created_at || 0).getTime();
  const isLatest = thisTime >= lastTime || Number(room.lastMessage?.id) === Number(message.id);
  const viewing = state.activeRoomId === roomId && document.visibilityState === "visible";
  const patch = {};
  if (isLatest) {
    patch.lastMessage = message;
    patch.activityAt = message.created_at;
  }
  // System notices (group events, disappearing-timer changes) never count as unread and never notify.
  if (firstTime && !isOwn && !message.is_deleted && !isGroupEvent(message) && !isSystemMessage(message)) {
    if (viewing) markRoomRead(roomId);
    else {
      patch.unread = Number(room.unread || 0) + 1;
      // WhatsApp shows "@" on the chat until a mention of me is read.
      if ((message.mentions || []).map(Number).includes(Number(state.me?.id))) patch.unreadMention = true;
    }
    onNew?.(message, room);
  }
  if (Object.keys(patch).length) dispatch({ type: "rooms/patch", roomId, patch });
}

export function applyReceipt(roomId, messageId, { is_delivered, is_read }) {
  const patch = { is_delivered: Boolean(is_delivered), is_read: Boolean(is_read) };
  dispatch({ type: "messages/patch", roomId, id: messageId, patch });
  const room = getState().rooms[roomId];
  if (room && Number(room.lastMessage?.id) === Number(messageId)) {
    dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: { ...room.lastMessage, ...patch } } });
  }
}

export function applyDeleted(roomId, messageId) {
  const tombstone = {
    is_deleted: true,
    content: "",
    attachments: [],
    voice_note: null,
    reactions: [],
    is_pinned: false,
    is_starred: false,
    is_edited: false,
  };
  dispatch({ type: "messages/patch", roomId, id: messageId, patch: tombstone });
  const room = getState().rooms[roomId];
  if (room && Number(room.lastMessage?.id) === Number(messageId)) {
    dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: { ...room.lastMessage, ...tombstone } } });
  }
}

export function applyReaction(roomId, { message_id, user_id, emoji, sender_phone }) {
  dispatch({
    type: "messages/patch",
    roomId,
    id: Number(message_id),
    patch: (item) => {
      const others = (item.reactions || []).filter((reaction) => Number(reaction.user_id) !== Number(user_id));
      return { reactions: emoji ? [...others, { user_id, emoji, sender_phone }] : others };
    },
  });
}

/** Merge a server "patch" event (poll results, view once opened…) into a message. */
export function applyMessagePatch(roomId, messageId, patch) {
  if (!patch || typeof patch !== "object") return;
  dispatch({ type: "messages/patch", roomId, id: Number(messageId), patch });
  const room = getState().rooms[roomId];
  if (room && Number(room.lastMessage?.id) === Number(messageId)) {
    dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: { ...room.lastMessage, ...patch } } });
  }
}

/**
 * Disappearing messages: drop expired messages from every loaded chat right
 * away (the server already hides them); refresh the list if a chat's last
 * message disappeared.
 */
export function sweepExpiredMessages() {
  const state = getState();
  const now = Date.now();
  const expired = (message) => message?.expires_at && new Date(message.expires_at).getTime() <= now;
  Object.entries(state.messages).forEach(([roomId, entry]) => {
    const ids = (entry?.items || []).filter(expired).map((message) => message.id).filter(Boolean);
    if (ids.length) dispatch({ type: "messages/remove", roomId: Number(roomId), ids });
  });
  if (Object.values(state.rooms).some((room) => expired(room.lastMessage))) scheduleRoomsReload(0);
}

/* ----------------------------------------------------------------------------
 * Sending
 * ------------------------------------------------------------------------- */

function optimistic(roomId, fields) {
  const me = getState().me;
  const clientId = newClientId();
  const message = {
    id: null,
    client_message_id: clientId,
    room_id: roomId,
    sender: me,
    message_type: "TEXT",
    content: "",
    attachments: [],
    reactions: [],
    created_at: new Date().toISOString(),
    is_delivered: false,
    is_read: false,
    _pending: true,
    ...fields,
  };
  dispatch({ type: "messages/upsert", roomId, message });
  const room = getState().rooms[roomId];
  if (room) dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: message, activityAt: message.created_at } });
  return message;
}

function settle(roomId, clientId, saved) {
  dispatch({ type: "messages/upsert", roomId, message: { ...saved, client_message_id: saved.client_message_id || clientId } });
  const room = getState().rooms[roomId];
  if (room && (room.lastMessage?.client_message_id === clientId || !room.lastMessage || new Date(saved.created_at) >= new Date(room.lastMessage.created_at))) {
    dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: saved, activityAt: saved.created_at } });
  }
  if (!room) scheduleRoomsReload(0);
}

function fail(roomId, clientId, error) {
  dispatch({ type: "messages/patch", roomId, clientId, patch: { _pending: false, _failed: true, _error: errorMessage(error) } });
  toast.error(errorMessage(error, "Message not sent."));
}

/**
 * Send a text message. ``mentions`` are user ids @mentioned in a group;
 * ``linkPreview`` is the composer's preview card (``false`` when the user
 * removed it, so the server stores none).
 */
export async function sendText(roomId, text, replyTo, { mentions = [], linkPreview } = {}) {
  const content = text.trim();
  if (!content) return;
  const draft = optimistic(roomId, {
    content,
    mentions,
    link_preview: linkPreview || null,
    reply_to: replyTo ? { id: replyTo.id, content: replyTo.content, sender_id: replyTo.sender?.id, message_type: replyTo.message_type, is_view_once: replyTo.is_view_once } : null,
    _retry: { kind: "text", content, replyToId: replyTo?.id, mentions, linkPreview },
  });
  try {
    const saved = await messageApi.send({
      room: roomId,
      content,
      reply_to: replyTo?.id,
      client_message_id: draft.client_message_id,
      mentions,
      link_preview: linkPreview === false ? false : undefined,
    });
    settle(roomId, draft.client_message_id, saved);
  } catch (error) {
    fail(roomId, draft.client_message_id, error);
  }
}

export function messageTypeForFile(file) {
  const kind = attachmentKind({ mime_type: file.type, file_name: file.name });
  if (kind === "image") return "IMAGE";
  if (kind === "video") return "VIDEO";
  return "DOCUMENT";
}

/** A GIF from the GIF tab (GIPHY): sent as a small JSON card, played from GIPHY's CDN. */
export function sendGif(roomId, gif, replyTo) {
  const payload = { kind: "gif", mp4: gif.mp4, still: gif.still || "", width: gif.width || null, height: gif.height || null, title: gif.title || "" };
  return sendText(roomId, GIF_PREFIX + JSON.stringify(payload), replyTo);
}

/** A sticker: a small transparent image shown without a bubble. */
export function sendSticker(roomId, file, replyTo) {
  return sendFile(roomId, file, { messageType: "STICKER", replyTo });
}

/** Upload one file as its own message (WhatsApp sends each media separately). */
export async function sendFile(roomId, file, { caption = "", replyTo, viewOnce = false, mentions = [], messageType = null } = {}) {
  const previewUrl = URL.createObjectURL(file);
  const type = messageType || messageTypeForFile(file);
  const draft = optimistic(roomId, {
    message_type: type,
    content: caption,
    is_view_once: viewOnce,
    view_once_opened_by: [],
    mentions,
    attachments: [{ id: `local-${Date.now()}`, file: previewUrl, file_name: file.name, file_size: file.size, mime_type: file.type }],
    _progress: 0,
    _retry: { kind: "file", file, caption, replyToId: replyTo?.id, viewOnce, mentions, messageType },
  });
  try {
    const saved = await messageApi.upload(
      {
        room: roomId,
        file,
        message_type: type,
        content: caption,
        reply_to: replyTo?.id,
        client_message_id: draft.client_message_id,
        view_once: viewOnce,
        mentions,
      },
      (event) => {
        if (!event.total) return;
        dispatch({ type: "messages/patch", roomId, clientId: draft.client_message_id, patch: { _progress: Math.round((event.loaded / event.total) * 100) } });
      },
    );
    settle(roomId, draft.client_message_id, saved);
    window.setTimeout(() => URL.revokeObjectURL(previewUrl), 30000);
  } catch (error) {
    fail(roomId, draft.client_message_id, error);
  }
}

export async function sendVoice(roomId, blob, seconds, waveform, viewOnce = false) {
  const extension = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
  const file = new File([blob], `voice-${Date.now()}.${extension}`, { type: blob.type || "audio/webm" });
  const previewUrl = URL.createObjectURL(blob);
  const draft = optimistic(roomId, {
    message_type: "VOICE",
    voice_note: { audio: viewOnce ? null : previewUrl, duration: seconds, waveform },
    is_view_once: viewOnce,
    _retry: { kind: "voice", blob, seconds, waveform, viewOnce },
  });
  try {
    const saved = await messageApi.voice({ room: roomId, audio: file, duration: Math.max(1, Math.round(seconds)), waveform, viewOnce });
    // The voice endpoint has no client id; replace the draft explicitly.
    dispatch({ type: "messages/remove", roomId, ids: [draft.client_message_id] });
    settle(roomId, draft.client_message_id, saved);
  } catch (error) {
    fail(roomId, draft.client_message_id, error);
  }
}

export function retryMessage(roomId, message) {
  const retry = message._retry;
  if (!retry) return;
  dispatch({ type: "messages/remove", roomId, ids: [message.client_message_id] });
  const replyTo = retry.replyToId ? { id: retry.replyToId } : undefined;
  if (retry.kind === "text") sendText(roomId, retry.content, replyTo, { mentions: retry.mentions, linkPreview: retry.linkPreview });
  if (retry.kind === "file") sendFile(roomId, retry.file, { caption: retry.caption, replyTo, viewOnce: retry.viewOnce, mentions: retry.mentions, messageType: retry.messageType });
  if (retry.kind === "poll") sendPoll(roomId, retry.poll);
  if (retry.kind === "location") sendLocation(roomId, retry.location);
  if (retry.kind === "voice") sendVoice(roomId, retry.blob, retry.seconds, retry.waveform, retry.viewOnce);
}

/** Send a poll: ``{ question, options: [text], allow_multiple }``. */
export async function sendPoll(roomId, poll) {
  const draft = optimistic(roomId, {
    message_type: "POLL",
    content: poll.question,
    poll: {
      id: null,
      question: poll.question,
      allow_multiple: Boolean(poll.allow_multiple),
      options: poll.options.map((text, index) => ({ id: `local-${index}`, text, voters: [], count: 0 })),
      total_voters: 0,
    },
    _retry: { kind: "poll", poll },
  });
  try {
    const saved = await messageApi.send({ room: roomId, message_type: "POLL", content: poll, client_message_id: draft.client_message_id });
    settle(roomId, draft.client_message_id, saved);
    return true;
  } catch (error) {
    fail(roomId, draft.client_message_id, error);
    return false;
  }
}

/** Vote / change / remove my vote (tap the chosen option again to unvote). */
export async function votePoll(roomId, message, optionId) {
  const poll = message.poll;
  const me = getState().me;
  if (!poll || !message.id || !me) return;
  const current = myPollVotes(poll, me.id);
  let next;
  if (poll.allow_multiple) next = current.includes(optionId) ? current.filter((id) => id !== optionId) : [...current, optionId];
  else next = current.includes(optionId) ? [] : [optionId];
  const optimisticPoll = {
    ...poll,
    options: poll.options.map((option) => {
      const voters = (option.voters || []).filter((id) => Number(id) !== Number(me.id));
      if (next.includes(option.id)) voters.push(me.id);
      return { ...option, voters, count: voters.length };
    }),
  };
  optimisticPoll.total_voters = new Set(optimisticPoll.options.flatMap((option) => option.voters.map(Number))).size;
  applyMessagePatch(roomId, message.id, { poll: optimisticPoll });
  try {
    const result = await messageApi.vote(message.id, next);
    applyMessagePatch(roomId, message.id, { poll: result.poll });
  } catch (error) {
    applyMessagePatch(roomId, message.id, { poll });
    toast.error(errorMessage(error, "Couldn't save your vote."));
  }
}

/** Share a location: ``{ latitude, longitude, accuracy?, name?, address? }``. */
export async function sendLocation(roomId, location) {
  const draft = optimistic(roomId, {
    message_type: "LOCATION",
    content: { address: "", ...location },
    _retry: { kind: "location", location },
  });
  try {
    const saved = await messageApi.send({ room: roomId, message_type: "LOCATION", content: location, client_message_id: draft.client_message_id });
    settle(roomId, draft.client_message_id, saved);
    return true;
  } catch (error) {
    fail(roomId, draft.client_message_id, error);
    return false;
  }
}

/** Change the chat's disappearing messages timer (0 = off). */
export async function setDisappearing(roomId, seconds) {
  const previous = getState().rooms[roomId]?.disappearingSeconds || 0;
  if (previous === seconds) return true;
  dispatch({ type: "rooms/patch", roomId, patch: { disappearingSeconds: seconds } });
  try {
    const result = await chatApi.setDisappearing(roomId, seconds);
    if (result?.message) receiveMessage(roomId, result.message);
    return true;
  } catch (error) {
    dispatch({ type: "rooms/patch", roomId, patch: { disappearingSeconds: previous } });
    toast.error(errorMessage(error));
    return false;
  }
}

export async function editMessage(roomId, message, content) {
  const previous = message.content;
  dispatch({ type: "messages/patch", roomId, id: message.id, patch: { content, is_edited: true } });
  try {
    await messageApi.edit(message.id, content);
  } catch (error) {
    dispatch({ type: "messages/patch", roomId, id: message.id, patch: { content: previous } });
    toast.error(errorMessage(error));
  }
}

export async function reactTo(roomId, message, emoji) {
  const me = getState().me;
  const mine = (message.reactions || []).find((reaction) => Number(reaction.user_id) === Number(me.id));
  const next = mine?.emoji === emoji ? "" : emoji;
  applyReaction(roomId, { message_id: message.id, user_id: me.id, emoji: next, sender_phone: me.phone_number });
  try {
    await messageApi.react(message.id, next);
  } catch (error) {
    applyReaction(roomId, { message_id: message.id, user_id: me.id, emoji: mine?.emoji || "" });
    toast.error(errorMessage(error));
  }
}

export async function toggleStar(roomId, messages, starred) {
  messages.forEach((message) => dispatch({ type: "messages/patch", roomId, id: message.id, patch: { is_starred: starred } }));
  try {
    await Promise.all(messages.map((message) => messageApi.star(message.id, starred)));
    window.dispatchEvent(new Event("mhtalk:starred-changed"));
    toast(starred ? (messages.length > 1 ? "Messages starred" : "Message starred") : "Unstarred");
  } catch (error) {
    messages.forEach((message) => dispatch({ type: "messages/patch", roomId, id: message.id, patch: { is_starred: !starred } }));
    toast.error(errorMessage(error));
  }
}

export async function togglePinMessage(roomId, message) {
  const next = !message.is_pinned;
  dispatch({ type: "messages/patch", roomId, id: message.id, patch: { is_pinned: next } });
  try {
    await messageApi.pin(message.id, next);
    // The server keeps 3 pins per chat and may have unpinned the oldest one.
    window.dispatchEvent(new CustomEvent("mhtalk:pins-changed", { detail: { roomId } }));
    if (next) toast("Message pinned");
  } catch (error) {
    dispatch({ type: "messages/patch", roomId, id: message.id, patch: { is_pinned: !next } });
    toast.error(errorMessage(error));
  }
}

export async function deleteMessages(roomId, messages, mode) {
  const ids = messages.map((message) => message.id).filter(Boolean);
  const localOnly = messages.filter((message) => !message.id).map((message) => message.client_message_id);
  if (localOnly.length) dispatch({ type: "messages/remove", roomId, ids: localOnly });
  if (!ids.length) return true;
  try {
    if (mode === "everyone") {
      await messageApi.deleteForEveryone(roomId, ids);
      ids.forEach((id) => applyDeleted(roomId, id));
    } else {
      await messageApi.deleteForMe(ids);
      dispatch({ type: "messages/remove", roomId, ids });
      scheduleRoomsReload();
    }
    return true;
  } catch (error) {
    toast.error(errorMessage(error));
    return false;
  }
}

export async function forwardMessages(messages, roomIds) {
  let sent = 0;
  for (const roomId of roomIds) {
    for (const message of messages) {
      try {
        const saved = await messageApi.forward(message.id, roomId);
        if (saved) receiveMessage(roomId, saved);
        sent += 1;
      } catch (error) {
        toast.error(errorMessage(error));
      }
    }
  }
  if (sent) toast.success(sent > 1 ? `${sent} messages forwarded` : "Message forwarded");
  scheduleRoomsReload();
}

/* ----------------------------------------------------------------------------
 * Chat-level actions
 * ------------------------------------------------------------------------- */

async function roomToggle(roomId, patch, request, successText) {
  const previous = getState().rooms[roomId];
  if (!previous) return;
  const rollback = Object.fromEntries(Object.keys(patch).map((key) => [key, previous[key]]));
  dispatch({ type: "rooms/patch", roomId, patch });
  try {
    await request();
    if (successText) toast(successText);
  } catch (error) {
    dispatch({ type: "rooms/patch", roomId, patch: rollback });
    toast.error(errorMessage(error));
  }
}

export const archiveRoom = (roomId, archived) =>
  roomToggle(roomId, archived ? { isArchived: true, isPinned: false } : { isArchived: false }, () => chatApi.archive(roomId, archived), archived ? "Chat archived" : "Chat unarchived");

export async function archiveRooms(roomIds, archived) {
  roomIds.forEach((roomId) => dispatch({ type: "rooms/patch", roomId, patch: { isArchived: archived, ...(archived ? { isPinned: false } : {}) } }));
  try {
    await chatApi.archiveMany(roomIds, archived);
    toast(`${roomIds.length} chat${roomIds.length > 1 ? "s" : ""} ${archived ? "archived" : "unarchived"}`);
  } catch (error) {
    toast.error(errorMessage(error));
    loadRooms();
  }
}

export const pinRoom = (roomId, pinned) =>
  roomToggle(roomId, { isPinned: pinned, pinnedAt: pinned ? new Date().toISOString() : null }, () => chatApi.pin(roomId, pinned), pinned ? "Chat pinned" : "Chat unpinned");

export const favoriteRoom = (roomId, favorite) =>
  roomToggle(roomId, { isFavorite: favorite }, () => chatApi.favorite(roomId, favorite), favorite ? "Added to Favorites" : "Removed from Favorites");

export async function muteRoom(roomId, duration) {
  const muted = duration !== "off";
  await roomToggle(roomId, { isMuted: muted }, () => chatApi.mute(roomId, duration), muted ? "Notifications muted" : "Notifications unmuted");
}

export async function markAllRead() {
  Object.values(getState().rooms).forEach((room) => {
    if (room.unread) dispatch({ type: "rooms/patch", roomId: room.id, patch: { unread: 0 } });
  });
  try {
    await chatApi.markAllRead();
  } catch (error) {
    toast.error(errorMessage(error));
    loadRooms();
  }
}

export async function clearChat(roomId) {
  try {
    await chatApi.clear(roomId);
    dispatch({ type: "messages/set", roomId, items: [], hasMore: false });
    dispatch({ type: "rooms/patch", roomId, patch: { lastMessage: null, unread: 0 } });
    toast("Chat cleared");
  } catch (error) {
    toast.error(errorMessage(error));
  }
}

export async function deleteChat(roomId) {
  try {
    await chatApi.deleteForMe(roomId);
    dispatch({ type: "rooms/remove", roomId });
    dispatch({ type: "messages/clear", roomId });
    if (getState().activeRoomId === roomId) dispatch({ type: "activeRoom", roomId: null });
    toast("Chat deleted");
  } catch (error) {
    toast.error(errorMessage(error));
  }
}

export async function setBlocked(userId, block) {
  try {
    if (block) await chatApi.block(userId);
    else await chatApi.unblock(userId);
    const current = getState().blocked;
    dispatch({ type: "blocked", ids: block ? [...new Set([...current, Number(userId)])] : current.filter((id) => id !== Number(userId)) });
    toast(block ? "Contact blocked" : "Contact unblocked");
  } catch (error) {
    toast.error(errorMessage(error));
  }
}

/** Open (or create) the 1:1 chat with a user and return its room id. */
export async function openChatWith(user) {
  const existing = Object.values(getState().rooms).find((room) => !room.isGroup && Number(room.otherUser?.id) === Number(user.id));
  if (existing) return existing.id;
  const raw = await chatApi.openPrivate(user.id);
  const room = normalizeRoom(raw, myId());
  dispatch({ type: "rooms/upsert", room: { ...room, _pinnedOpen: true } });
  return room.id;
}
