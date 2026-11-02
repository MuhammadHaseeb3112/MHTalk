import { useCallback, useRef, useSyncExternalStore } from "react";

/**
 * Minimal external store (Redux-like) with selector subscriptions.
 *
 * Components read with `useStore(selector)` and only re-render when the
 * selected slice changes (shallow comparison for arrays/objects), which keeps
 * the chat list and message list fast while typing/presence events stream in.
 *
 * The REST API is the source of truth: realtime events patch this state and
 * a reconnect triggers a full re-sync (see services/realtime.js).
 */

export const initialState = {
  me: null,
  contacts: [], // saved contacts from /accounts/contacts/
  rooms: {}, // id -> normalised room
  roomsLoaded: false,
  messages: {}, // roomId -> { items: [], loaded, hasMore, loading }
  typing: {}, // roomId -> { userId: expiresAt }
  presence: {}, // userId -> { is_online, last_seen }
  blocked: [], // user ids I blocked
  statusFeed: [],
  myStatuses: [],
  statusLoaded: false,
  calls: [],
  missedUnseen: 0,
  activeCalls: {}, // roomId -> ringing/ongoing group call (drives the "Join" banners)
  currentCallId: null, // the group call I'm in (no "Join" button for it)
  connection: "connecting", // connecting | online | offline
  activeRoomId: null,
};

function patchRoom(state, roomId, patch) {
  const room = state.rooms[roomId];
  if (!room) return state;
  return { ...state, rooms: { ...state.rooms, [roomId]: { ...room, ...patch } } };
}

function sortMessages(items) {
  return items.sort((a, b) => {
    const ta = new Date(a.created_at).getTime();
    const tb = new Date(b.created_at).getTime();
    if (ta !== tb) return ta - tb;
    return (Number(a.id) || 0) - (Number(b.id) || 0);
  });
}

/** Insert or merge a message; reconciles optimistic copies via client_message_id. */
function upsertMessage(items, message) {
  const index = items.findIndex(
    (item) =>
      (message.id && item.id === message.id) ||
      (message.client_message_id && item.client_message_id === message.client_message_id),
  );
  if (index >= 0) {
    const next = items.slice();
    next[index] = { ...items[index], ...message, _pending: false, _failed: false };
    return next;
  }
  return sortMessages([...items, message]);
}

export function reducer(state, action) {
  switch (action.type) {
    case "reset":
      return { ...initialState };
    case "me":
      return { ...state, me: action.me };
    case "activeRoom":
      return state.activeRoomId === action.roomId ? state : { ...state, activeRoomId: action.roomId };
    case "connection":
      return state.connection === action.status ? state : { ...state, connection: action.status };
    case "contacts":
      return { ...state, contacts: action.contacts };
    case "blocked":
      return { ...state, blocked: action.ids };

    case "rooms/set": {
      const rooms = {};
      action.rooms.forEach((room) => {
        const previous = state.rooms[room.id];
        // Preserve a locally-zeroed unread counter for the open chat.
        rooms[room.id] = previous?._keepRead ? { ...room, unread: 0, unreadMention: false, _keepRead: true } : room;
      });
      // Keep a conversation that was opened but is not listed (e.g. new or deleted-from-list).
      Object.values(state.rooms).forEach((room) => {
        if (!rooms[room.id] && room._pinnedOpen) rooms[room.id] = room;
      });
      return { ...state, rooms, roomsLoaded: true };
    }
    case "rooms/upsert": {
      const previous = state.rooms[action.room.id];
      return {
        ...state,
        rooms: { ...state.rooms, [action.room.id]: { ...previous, ...action.room } },
      };
    }
    case "rooms/patch":
      return patchRoom(state, action.roomId, action.patch);
    case "rooms/remove": {
      const rooms = { ...state.rooms };
      delete rooms[action.roomId];
      return { ...state, rooms };
    }

    case "messages/loading":
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: { items: [], hasMore: true, ...state.messages[action.roomId], loading: true, error: "" },
        },
      };
    case "messages/set":
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: { items: sortMessages(action.items.slice()), loaded: true, loading: false, hasMore: action.hasMore, error: "" },
        },
      };
    case "messages/error":
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: { items: [], ...state.messages[action.roomId], loading: false, error: action.error },
        },
      };
    case "messages/prepend": {
      const current = state.messages[action.roomId] || { items: [] };
      const known = new Set(current.items.map((item) => item.id));
      const older = action.items.filter((item) => !known.has(item.id));
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: { ...current, items: sortMessages([...older, ...current.items]), hasMore: action.hasMore, loading: false },
        },
      };
    }
    case "messages/upsert": {
      const current = state.messages[action.roomId];
      if (!current) return state;
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: { ...current, items: upsertMessage(current.items, action.message) } },
      };
    }
    case "messages/patch": {
      const current = state.messages[action.roomId];
      if (!current) return state;
      const items = current.items.map((item) =>
        item.id === action.id || (action.clientId && item.client_message_id === action.clientId)
          ? { ...item, ...(typeof action.patch === "function" ? action.patch(item) : action.patch) }
          : item,
      );
      return { ...state, messages: { ...state.messages, [action.roomId]: { ...current, items } } };
    }
    case "messages/remove": {
      const current = state.messages[action.roomId];
      if (!current) return state;
      const ids = new Set(action.ids);
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: { ...current, items: current.items.filter((item) => !ids.has(item.id) && !ids.has(item.client_message_id)) },
        },
      };
    }
    case "messages/clear": {
      const messages = { ...state.messages };
      delete messages[action.roomId];
      return { ...state, messages };
    }

    case "typing": {
      const roomTyping = { ...(state.typing[action.roomId] || {}) };
      if (action.isTyping) roomTyping[action.userId] = Date.now() + 6000;
      else delete roomTyping[action.userId];
      return { ...state, typing: { ...state.typing, [action.roomId]: roomTyping } };
    }
    case "typing/expire": {
      const now = Date.now();
      let changed = false;
      const typing = {};
      Object.entries(state.typing).forEach(([roomId, users]) => {
        const kept = {};
        Object.entries(users).forEach(([userId, expires]) => {
          if (expires > now) kept[userId] = expires;
          else changed = true;
        });
        typing[roomId] = kept;
      });
      return changed ? { ...state, typing } : state;
    }
    case "presence": {
      const previous = state.presence[action.userId];
      if (previous && previous.is_online === action.is_online && previous.last_seen === action.last_seen) return state;
      return {
        ...state,
        presence: { ...state.presence, [action.userId]: { is_online: action.is_online, last_seen: action.last_seen } },
      };
    }

    case "status/set":
      return { ...state, statusFeed: action.feed, myStatuses: action.mine, statusLoaded: true };
    case "calls/set":
      return { ...state, calls: action.calls };
    case "calls/missed":
      return { ...state, missedUnseen: action.count };
    case "calls/active":
      return { ...state, activeCalls: action.byRoom };
    case "calls/current":
      return state.currentCallId === action.callId ? state : { ...state, currentCallId: action.callId };
    default:
      return state;
  }
}

function shallowEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || typeof b !== "object" || !a || !b) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => Object.is(a[key], b[key]));
}

function createStore(reducerFn, preloaded) {
  let state = preloaded;
  const listeners = new Set();
  return {
    getState: () => state,
    dispatch(action) {
      const next = reducerFn(state, action);
      if (next !== state) {
        state = next;
        listeners.forEach((listener) => listener());
      }
      return action;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const store = createStore(reducer, initialState);
export const dispatch = store.dispatch;
export const getState = store.getState;

/** Subscribe to a slice of the store. */
export function useStore(selector) {
  const cache = useRef({ hasValue: false, value: undefined });
  const getSnapshot = useCallback(() => {
    const next = selector(store.getState());
    if (cache.current.hasValue && shallowEqual(cache.current.value, next)) return cache.current.value;
    cache.current = { hasValue: true, value: next };
    return next;
  }, [selector]);
  return useSyncExternalStore(store.subscribe, getSnapshot, getSnapshot);
}
