import { refreshAccessToken, socketUrl, tokens } from "../api/client";
import {
  applyDeleted,
  applyMessagePatch,
  sweepExpiredMessages,
  applyReaction,
  applyReceipt,
  loadCalls,
  loadContacts,
  loadMessages,
  receiveMessage,
  refreshRoom,
  scheduleRoomsReload,
  scheduleStatusReload,
  bootstrap,
} from "../store/actions";
import { dispatch, getState } from "../store/store";
import { roomTitle, contactsByUser, displayUserName, previewText } from "../utils/messages";
import { playIncomingSound, showDesktopNotification } from "./notify";
import { toast } from "./toast";

/**
 * Realtime controller.
 *
 * One **inbox** socket per tab (ws/chat/inbox/) carries everything the
 * sidebar needs: new messages for every chat, receipts, typing, presence and
 * "re-sync" nudges. A **room** socket (ws/chat/<id>/) is opened only for the
 * conversation on screen; it carries edits, deletions, reactions and typing.
 *
 * Both sockets reconnect with exponential backoff, refresh an expired JWT
 * before reconnecting, and trigger a REST re-sync after a reconnect so that
 * nothing missed while offline is lost (the database stays the source of
 * truth).
 */

const MAX_BACKOFF = 15000;

/**
 * Every per-recipient receipt (one group member read / received a message)
 * is announced so an open "Message info" panel can refresh live, even when
 * the message's overall ticks don't change.
 */
function announceReceipt(messageId) {
  const id = Number(messageId);
  if (id) window.dispatchEvent(new CustomEvent("mhtalk:receipt", { detail: id }));
}

export class ManagedSocket {
  constructor({ path, onMessage, onOpen, onStatus, onUnauthorized, ping = true }) {
    this.path = path;
    this.ping = ping;
    this.onMessage = onMessage;
    this.onOpen = onOpen;
    this.onStatus = onStatus;
    this.onUnauthorized = onUnauthorized;
    this.socket = null;
    this.attempt = 0;
    this.closedByUser = false;
    this.timer = null;
    this.pingTimer = null;
    this.queue = [];
    this.everConnected = false;
  }

  /** Resolves when the socket is open (or rejects after `timeout` ms). */
  whenOpen(timeout = 6000) {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const check = () => {
        if (this.socket?.readyState === WebSocket.OPEN) resolve();
        else if (Date.now() - started > timeout) reject(new Error("Connection timed out."));
        else window.setTimeout(check, 80);
      };
      check();
    });
  }

  connect() {
    this.closedByUser = false;
    if (!tokens.access) return;
    const socket = new WebSocket(socketUrl(this.path));
    this.socket = socket;
    this.onStatus?.("connecting");

    socket.onopen = () => {
      if (this.socket !== socket) return;
      const reconnected = this.everConnected;
      this.everConnected = true;
      this.attempt = 0;
      this.onStatus?.("online");
      this.flush();
      if (this.ping) this.pingTimer = window.setInterval(() => this.send({ type: "ping" }, { queue: false }), 25000);
      this.onOpen?.({ reconnected });
    };
    socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      this.onMessage(data);
    };
    socket.onclose = async (event) => {
      window.clearInterval(this.pingTimer);
      if (this.socket !== socket || this.closedByUser) return;
      this.onStatus?.("offline");
      // 4001 = rejected token: refresh before retrying.
      if (event.code === 4001) {
        try {
          await refreshAccessToken();
        } catch {
          this.onUnauthorized?.();
          return;
        }
      }
      if (event.code === 4003 || event.code === 4004) return; // not a member / room gone
      this.scheduleReconnect();
    };
    socket.onerror = () => {
      /* onclose handles retries */
    };
  }

  scheduleReconnect() {
    window.clearTimeout(this.timer);
    const delay = Math.min(MAX_BACKOFF, 800 * 2 ** this.attempt) + Math.random() * 400;
    this.attempt += 1;
    this.timer = window.setTimeout(() => this.connect(), delay);
  }

  reconnectNow() {
    if (this.closedByUser) return;
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;
    window.clearTimeout(this.timer);
    this.connect();
  }

  send(payload, { queue = true } = {}) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
      return true;
    }
    if (queue) this.queue.push(payload);
    return false;
  }

  flush() {
    const pending = this.queue.splice(0);
    pending.forEach((payload) => this.send(payload, { queue: false }));
  }

  close() {
    this.closedByUser = true;
    window.clearTimeout(this.timer);
    window.clearInterval(this.pingTimer);
    const socket = this.socket;
    this.socket = null;
    if (!socket) return;
    if (socket.readyState === WebSocket.CONNECTING) {
      // Closing a socket that is still connecting makes the browser log
      // "WebSocket is closed before the connection is established" (this
      // happens on every React StrictMode remount and on fast logouts).
      // Let it finish the handshake quietly, then close it.
      socket.onmessage = null;
      socket.onerror = null;
      socket.onopen = () => socket.close(1000);
    } else if (socket.readyState === WebSocket.OPEN) {
      socket.close(1000);
    }
  }
}

function notifyNewMessage(message, room) {
  const state = getState();
  // Like WhatsApp, an @mention of me notifies even in a muted group.
  const mentionsMe = (message.mentions || []).map(Number).includes(Number(state.me?.id));
  if (!room || (room.isMuted && !mentionsMe)) return;
  const viewing = state.activeRoomId === room.id && document.visibilityState === "visible";
  if (viewing) return;
  playIncomingSound();
  const contactMap = contactsByUser(state.contacts);
  const title = roomTitle(room, contactMap, state.me);
  const nameOf = (id) => {
    const user = room.participants?.find((p) => Number(p.user?.id) === Number(id))?.user;
    return user ? displayUserName(user, contactMap) : "Someone";
  };
  let body = previewText(message, state.me?.id, nameOf);
  if (room.isGroup) body = `${nameOf(message.sender?.id)}: ${body}`;
  // "@+92300…" tokens read better as "@Name" in the notification.
  (message.mentions || []).forEach((id) => {
    const user = room.participants?.find((p) => Number(p.user?.id) === Number(id))?.user;
    if (user?.phone_number) body = body.split(`@${user.phone_number}`).join(`@${Number(id) === Number(state.me?.id) ? "You" : nameOf(id)}`);
  });
  showDesktopNotification(title, body, () => {
    window.dispatchEvent(new CustomEvent("mhtalk:open-room", { detail: room.id }));
  });
}

class Realtime {
  constructor() {
    this.inbox = null;
    this.room = null;
    this.roomId = null;
    this.typingSweep = null;
    this.onSessionExpired = null;
    this.handleVisibility = this.handleVisibility.bind(this);
    this.handleOnline = this.handleOnline.bind(this);
  }

  start({ onSessionExpired } = {}) {
    this.stop();
    this.onSessionExpired = onSessionExpired;
    this.inbox = new ManagedSocket({
      path: "/ws/chat/inbox/",
      onMessage: (data) => this.handleInbox(data),
      onStatus: (status) => dispatch({ type: "connection", status }),
      onOpen: ({ reconnected }) => {
        if (reconnected) this.resync();
      },
      onUnauthorized: () => this.onSessionExpired?.(),
    });
    this.inbox.connect();
    this.typingSweep = window.setInterval(() => dispatch({ type: "typing/expire" }), 2000);
    // Disappearing messages vanish on screen as soon as they expire.
    this.expirySweep = window.setInterval(sweepExpiredMessages, 15000);
    document.addEventListener("visibilitychange", this.handleVisibility);
    window.addEventListener("online", this.handleOnline);
  }

  stop() {
    this.inbox?.close();
    this.room?.close();
    this.inbox = null;
    this.room = null;
    this.roomId = null;
    window.clearInterval(this.typingSweep);
    window.clearInterval(this.expirySweep);
    document.removeEventListener("visibilitychange", this.handleVisibility);
    window.removeEventListener("online", this.handleOnline);
  }

  handleVisibility() {
    if (document.visibilityState !== "visible") return;
    this.inbox?.reconnectNow();
    this.room?.reconnectNow();
  }

  handleOnline() {
    this.inbox?.reconnectNow();
    this.room?.reconnectNow();
  }

  /** Re-sync authoritative state after a reconnect. */
  resync() {
    bootstrap();
    const { activeRoomId } = getState();
    if (activeRoomId) loadMessages(activeRoomId);
  }

  openRoom(roomId) {
    if (this.roomId === roomId && this.room) return;
    this.room?.close();
    this.room = null;
    this.roomId = roomId;
    if (!roomId) return;
    this.room = new ManagedSocket({
      path: `/ws/chat/${roomId}/`,
      // The inbox socket already keeps the connection warm; older servers
      // treated a room "ping" as an empty message.
      ping: false,
      onMessage: (data) => this.handleRoom(roomId, data),
      onOpen: ({ reconnected }) => {
        if (reconnected) loadMessages(roomId);
      },
      onUnauthorized: () => this.onSessionExpired?.(),
    });
    this.room.connect();
  }

  sendTyping(isTyping) {
    this.room?.send({ type: "typing", is_typing: Boolean(isTyping) }, { queue: false });
  }

  handleInbox(data) {
    const me = getState().me;
    switch (data.type) {
      case "inbox.message": {
        const roomId = Number(data.room_id);
        const message = data.message;
        if (!roomId || !message) return;
        if (Number(message.sender?.id) !== Number(me?.id) && !message.is_delivered) {
          this.inbox.send({ type: "delivered", room_id: roomId, message_id: message.id }, { queue: false });
        }
        receiveMessage(roomId, message, { onNew: notifyNewMessage });
        break;
      }
      case "receipt":
        applyReceipt(Number(data.room_id), Number(data.message_id), data);
        announceReceipt(data.message_id);
        break;
      case "typing":
        dispatch({ type: "typing", roomId: Number(data.room_id), userId: Number(data.user_id), isTyping: data.is_typing });
        break;
      case "presence":
        dispatch({ type: "presence", userId: Number(data.user_id), is_online: Boolean(data.is_online), last_seen: data.last_seen || null });
        break;
      case "room.updated": {
        const roomId = Number(data.room_id);
        if (roomId && getState().rooms[roomId] && !["archived", "read", "pinned", "favorite", "muted"].includes(data.action)) {
          refreshRoom(roomId);
        } else {
          scheduleRoomsReload();
        }
        break;
      }
      case "profile.updated":
        scheduleRoomsReload(400);
        if (Number(data.user_id) === Number(me?.id)) window.dispatchEvent(new Event("mhtalk:me-changed"));
        break;
      case "contacts.updated":
        loadContacts();
        break;
      case "message.patch":
        applyMessagePatch(Number(data.room_id), Number(data.message_id), data.patch);
        break;
      case "account.deleted":
        // This account was deleted (here or on another device): sign out
        // before the server closes the socket.
        this.stop();
        window.dispatchEvent(new Event("mhtalk:signed-out"));
        break;
      case "status.updated":
        scheduleStatusReload();
        break;
      case "calls.updated":
        loadCalls();
        window.dispatchEvent(new CustomEvent("mhtalk:call-changed", { detail: data }));
        break;
      default:
        break;
    }
  }

  handleRoom(roomId, data) {
    switch (data.type) {
      case "message":
        if (data.message) receiveMessage(roomId, data.message, { onNew: notifyNewMessage });
        break;
      case "delivered":
      case "read":
        applyReceipt(roomId, Number(data.message_id), data);
        announceReceipt(data.message_id);
        break;
      case "edited":
        dispatch({ type: "messages/patch", roomId, id: Number(data.message_id), patch: { content: data.content, is_edited: true } });
        break;
      case "deleted":
        applyDeleted(roomId, Number(data.message_id));
        break;
      case "reaction":
        applyReaction(roomId, data);
        break;
      case "pin":
        dispatch({ type: "messages/patch", roomId, id: Number(data.message_id), patch: { is_pinned: Boolean(data.is_pinned) } });
        break;
      case "patch":
        applyMessagePatch(roomId, Number(data.message_id), data.patch);
        break;
      case "typing":
        dispatch({ type: "typing", roomId, userId: Number(data.user_id), isTyping: data.is_typing });
        break;
      case "presence":
        dispatch({ type: "presence", userId: Number(data.user_id), is_online: Boolean(data.is_online), last_seen: data.last_seen || null });
        break;
      case "error":
        if (data.message) toast.error(data.message);
        break;
      default:
        break;
    }
  }
}

export const realtime = new Realtime();

