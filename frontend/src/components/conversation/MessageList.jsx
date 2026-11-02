import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Lock, Timer } from "lucide-react";
import { loadOlderMessages } from "../../store/actions";
import { takePendingJump } from "../../services/jump";
import { toast } from "../../services/toast";
import { getState, useStore } from "../../store/store";
import { dayLabel, sameDay } from "../../utils/format";
import { displayUserName, groupEventText, isGroupEvent, isSystemMessage, senderColor, systemText } from "../../utils/messages";
import { Spinner } from "../common/ui";
import MessageBubble from "../messages/MessageBubble";

const GROUP_GAP_MS = 7 * 60 * 1000;
const EMPTY = { items: [], loaded: false, loading: true, hasMore: false };

/**
 * Scrollable message history.
 * - Day separators, "N unread messages" divider (captured when the chat opens)
 * - Bubble grouping (tail + sender name only on the first of a run)
 * - Loads older pages when scrolled near the top, preserving position
 * - Sticks to the bottom for new messages; otherwise shows a jump button
 */
export default function MessageList({ room, me, contactMap, selectMode, selectedIds, searchQuery, onAction, initialUnread }) {
  const state = useStore((s) => s.messages[room.id]) || EMPTY;
  const items = state.items;
  const scrollRef = useRef(null);
  const nearBottomRef = useRef(true);
  const prevHeightRef = useRef(0);
  const prevFirstIdRef = useRef(null);
  const prevCountRef = useRef(0);
  const [showJump, setShowJump] = useState(false);
  const [newWhileAway, setNewWhileAway] = useState(0);
  const [highlightId, setHighlightId] = useState(null);
  // Decide once where the unread divider goes (first unread incoming message).
  const computeMarker = () => {
    if (!(initialUnread > 0)) return null;
    const incoming = items.filter((item) => Number(item.sender?.id) !== Number(me.id) && !item.is_deleted && !isGroupEvent(item) && !isSystemMessage(item));
    return incoming[Math.max(0, incoming.length - initialUnread)]?.id ?? null;
  };
  const [unreadMarker, setUnreadMarker] = useState(() => (state.loaded ? computeMarker() : undefined));
  if (unreadMarker === undefined && state.loaded) setUnreadMarker(computeMarker());

  const nameOf = useCallback(
    (userId) => {
      if (Number(userId) === Number(me.id)) return "You";
      const user = room.participants.find((p) => Number(p.user?.id) === Number(userId))?.user;
      return user ? displayUserName(user, contactMap) : "Unknown";
    },
    [room.participants, contactMap, me.id],
  );
  const colorOf = useCallback((userId) => (Number(userId) === Number(me.id) ? "var(--accent)" : senderColor(userId)), [me.id]);
  const userOf = useCallback(
    (userId) => (Number(userId) === Number(me.id) ? me : room.participants.find((p) => Number(p.user?.id) === Number(userId))?.user || null),
    [room.participants, me],
  );
  // "@<phone>" token stored in the text -> highlighted "@Name".
  const mentionOf = useCallback(
    (userId) => {
      const user = userOf(userId);
      if (!user?.phone_number) return null;
      return { id: Number(userId), token: `@${user.phone_number}`, label: Number(userId) === Number(me.id) ? "You" : displayUserName(user, contactMap) };
    },
    [userOf, contactMap, me.id],
  );

  const scrollToBottom = useCallback((smooth = false) => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setNewWhileAway(0);
  }, []);

  // Initial position: unread divider if any, else bottom.
  const positionedRef = useRef(false);
  useLayoutEffect(() => {
    if (positionedRef.current || !state.loaded) return;
    positionedRef.current = true;
    const node = scrollRef.current;
    if (!node) return;
    const divider = node.querySelector(".unread-divider");
    if (divider) node.scrollTop = Math.max(0, divider.offsetTop - 80);
    else node.scrollTop = node.scrollHeight;
    prevHeightRef.current = node.scrollHeight;
    prevFirstIdRef.current = items[0]?.id ?? items[0]?.client_message_id;
    prevCountRef.current = items.length;
  }, [state.loaded, items]);

  // Images, videos and voice waveforms finish loading after the first layout and
  // make the list taller. While the reader is at the bottom, stay at the bottom.
  useEffect(() => {
    const node = scrollRef.current;
    const inner = node?.firstElementChild;
    if (!node || !inner || typeof ResizeObserver === "undefined") return undefined;
    let lastHeight = inner.offsetHeight;
    const observer = new ResizeObserver(() => {
      const height = inner.offsetHeight;
      const grew = height > lastHeight;
      lastHeight = height;
      if (grew && positionedRef.current && nearBottomRef.current && !node.querySelector(".unread-divider")) {
        node.scrollTop = node.scrollHeight;
      }
      prevHeightRef.current = node.scrollHeight;
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

  // Keep position when older messages are prepended; follow new ones at the bottom.
  useLayoutEffect(() => {
    const node = scrollRef.current;
    if (!node || !positionedRef.current) return;
    const firstId = items[0]?.id ?? items[0]?.client_message_id;
    const prepended = prevFirstIdRef.current && firstId !== prevFirstIdRef.current && items.length > prevCountRef.current;
    if (prepended) {
      node.scrollTop += node.scrollHeight - prevHeightRef.current;
    } else if (items.length > prevCountRef.current) {
      const last = items[items.length - 1];
      const own = Number(last?.sender?.id) === Number(me.id);
      if (own || nearBottomRef.current) scrollToBottom(!own);
      else setNewWhileAway((count) => count + (items.length - prevCountRef.current));
    }
    prevHeightRef.current = node.scrollHeight;
    prevFirstIdRef.current = firstId;
    prevCountRef.current = items.length;
  }, [items, me.id, scrollToBottom]);

  const onScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    nearBottomRef.current = distance < 120;
    setShowJump(distance > 400);
    if (distance < 120) setNewWhileAway(0);
    if (node.scrollTop < 300) {
      const current = getState().messages[room.id];
      if (current?.hasMore && !current.loading) loadOlderMessages(room.id);
    }
  }, [room.id]);

  // Scroll to a specific message (reply quote, search result, starred).
  // Older pages are loaded until the message is found or history ends.
  const jumpingRef = useRef(false);
  const jumpTo = useCallback(
    async (messageId) => {
      if (!messageId || jumpingRef.current) return;
      jumpingRef.current = true;
      try {
        for (let attempt = 0; attempt < 120; attempt += 1) {
          const container = scrollRef.current;
          if (!container) return;
          const node = container.querySelector(`[data-message-id="${messageId}"]`);
          if (node) {
            nearBottomRef.current = false;
            const top =
              node.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - container.clientHeight / 2 + node.offsetHeight / 2;
            container.scrollTo({ top: Math.max(0, top), behavior: attempt === 0 ? "smooth" : "auto" });
            setHighlightId(messageId);
            window.setTimeout(() => setHighlightId(null), 2200);
            return;
          }
          const current = getState().messages[room.id];
          if (!current?.loaded || current.loading) {
            await new Promise((resolve) => window.setTimeout(resolve, 120));
            continue;
          }
          if (!current.hasMore) {
            toast("This message isn't in the chat anymore.");
            return;
          }
          await loadOlderMessages(room.id);
          await new Promise((resolve) => window.setTimeout(resolve, 40));
        }
      } finally {
        jumpingRef.current = false;
      }
    },
    [room.id],
  );

  useEffect(() => {
    const handler = (event) => jumpTo(Number(event.detail));
    const onPending = (event) => {
      if (Number(event.detail?.roomId) !== Number(room.id)) return;
      const id = takePendingJump(room.id);
      if (id) jumpTo(id);
    };
    window.addEventListener("whatsup:jump-to", handler);
    window.addEventListener("whatsup:jump-pending", onPending);
    // A jump requested before this chat was opened.
    const id = takePendingJump(room.id);
    if (id) jumpTo(id);
    return () => {
      window.removeEventListener("whatsup:jump-to", handler);
      window.removeEventListener("whatsup:jump-pending", onPending);
    };
  }, [jumpTo, room.id]);

  const handleAction = useCallback(
    (type, message, payload) => {
      if (type === "jump") jumpTo(payload.id);
      else onAction(type, message, payload);
    },
    [jumpTo, onAction],
  );

  const rows = useMemo(() => {
    const result = [];
    items.forEach((message, index) => {
      const previous = items[index - 1];
      const newDay = !previous || !sameDay(previous.created_at, message.created_at);
      const system = isGroupEvent(message);
      const sameSender =
        previous &&
        !newDay &&
        !system &&
        !isGroupEvent(previous) &&
        !isSystemMessage(previous) &&
        Number(previous.sender?.id) === Number(message.sender?.id) &&
        new Date(message.created_at) - new Date(previous.created_at) < GROUP_GAP_MS &&
        message.id !== unreadMarker;
      result.push({ message, newDay, first: !sameSender, system });
    });
    return result;
  }, [items, unreadMarker]);

  return (
    <div className="messages" ref={scrollRef} onScroll={onScroll}>
      <div className="messages__inner">
        {state.loading && state.loaded ? (
          <div className="messages__older"><Spinner size={20} /></div>
        ) : null}
        {!state.loaded && state.loading ? (
          <div className="messages__loading"><Spinner /></div>
        ) : null}
        {state.error && !items.length ? <div className="system-pill system-pill--error">{state.error}</div> : null}
        {state.loaded && !state.hasMore ? (
          <div className="system-pill system-pill--info">
            <Lock size={12} /> Messages are stored on your MHTalk server and synced to your devices.
          </div>
        ) : null}

        {rows.map(({ message, newDay, first, system }) => {
          const isOwn = Number(message.sender?.id) === Number(me.id);
          const key = message.client_message_id && !message.id ? message.client_message_id : message.id;
          const senderUser = message.sender;
          return (
            <Fragment key={key}>
              {newDay ? <div className="day-divider"><span>{dayLabel(message.created_at)}</span></div> : null}
              {message.id && message.id === unreadMarker ? (
                <div className="unread-divider"><span>{initialUnread} unread message{initialUnread === 1 ? "" : "s"}</span></div>
              ) : null}
              {isSystemMessage(message) ? (
                <div className="system-notice" data-message-id={message.id || message.client_message_id}>
                  <button type="button" onClick={() => onAction("disappearing", message)}>
                    <Timer size={14} /> {systemText(message, me.id, nameOf)}
                  </button>
                </div>
              ) : system ? (
                // Group system message ("Alice changed this group's settings…").
                <div className="system-pill system-pill--event" data-message-id={message.id}>
                  {groupEventText(message, me.id, nameOf)}
                </div>
              ) : (
                <MessageBubble
                  message={message}
                  myId={me.id}
                  isOwn={isOwn}
                  showTail={first}
                  senderName={room.isGroup && first && !isOwn ? displayUserName(senderUser, contactMap) : isOwn ? "" : ""}
                  senderColor={senderColor(senderUser?.id)}
                  senderAvatar={senderUser?.profile?.profile_picture}
                  nameOf={nameOf}
                  colorOf={colorOf}
                  userOf={userOf}
                  mentionOf={mentionOf}
                  selectMode={selectMode}
                  selected={selectedIds.includes(message.id)}
                  highlighted={highlightId === message.id}
                  searchQuery={searchQuery}
                  onAction={handleAction}
                />
              )}
            </Fragment>
          );
        })}
      </div>
      {showJump || newWhileAway ? (
        <button type="button" className="jump-bottom" onClick={() => scrollToBottom(true)} aria-label="Scroll to latest message">
          {newWhileAway ? <span className="badge">{newWhileAway}</span> : null}
          <ChevronDown size={24} />
        </button>
      ) : null}
    </div>
  );
}
