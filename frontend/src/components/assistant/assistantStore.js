import { useSyncExternalStore } from "react";
import { errorMessage } from "../../api/client";
import { assistantApi } from "../../api/endpoints";
import { getState } from "../../store/store";

/**
 * MHTalk AI conversation, kept per user in this browser (localStorage).
 * The server only relays the conversation to the AI service.
 */
const listeners = new Set();
let state = { userId: null, messages: [], sending: false, status: null };

function key(userId) {
  return `whatsup-ai-chat-${userId}`;
}

function emit(next) {
  state = { ...state, ...next };
  if (next.messages) {
    try {
      localStorage.setItem(key(state.userId), JSON.stringify(state.messages.slice(-60)));
    } catch {
      /* storage full or blocked */
    }
  }
  listeners.forEach((listener) => listener());
}

function ensureUser() {
  const userId = getState().me?.id || null;
  if (userId === state.userId) return;
  let messages;
  try {
    messages = JSON.parse(localStorage.getItem(key(userId)) || "[]");
  } catch {
    messages = [];
  }
  if (!Array.isArray(messages)) messages = [];
  state = { userId, messages, sending: false, status: state.status };
}

export function useAssistant() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => {
      ensureUser();
      return state;
    },
  );
}

export async function loadAssistantStatus() {
  try {
    emit({ status: await assistantApi.status() });
  } catch {
    emit({ status: { enabled: false } });
  }
}

export async function askAssistant(text) {
  ensureUser();
  const content = String(text || "").trim();
  if (!content || state.sending) return;
  const now = new Date().toISOString();
  const history = [...state.messages, { id: `u-${Date.now()}`, role: "user", content, at: now }];
  emit({ messages: history, sending: true });
  try {
    const data = await assistantApi.send(
      history.filter((item) => !item.error).map(({ role, content: body }) => ({ role, content: body })),
    );
    emit({
      messages: [...state.messages, { id: `a-${Date.now()}`, role: "assistant", content: data.reply, at: new Date().toISOString() }],
      sending: false,
    });
  } catch (error) {
    emit({
      messages: [...state.messages, { id: `e-${Date.now()}`, role: "assistant", content: errorMessage(error), error: true, at: new Date().toISOString() }],
      sending: false,
    });
  }
}

export function clearAssistant() {
  ensureUser();
  emit({ messages: [] });
}
