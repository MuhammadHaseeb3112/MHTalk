import { memo, useRef, useState } from "react";
import { BellOff, Ban, ChevronDown, FileText, Image, Mic, Phone, PhoneMissed, Pin, Video, Headphones, Sticker, Timer } from "lucide-react";
import { listTime } from "../../utils/format";
import { callSummary, messageKind, parseSpecial, previewText } from "../../utils/messages";
import { useStore } from "../../store/store";
import { Avatar, Checkbox, Menu } from "../common/ui";
import { ringFor, useStatusGroup } from "../status/statusRing";
import { openProfilePeek, openUserStatus } from "../status/profileOverlay";
import { requestJoinCall } from "../calls/groupCall";
import { buildRoomMenu } from "./roomMenu";
import { ClockIcon, DoubleTick, SingleTick } from "../common/Icons";

const KIND_ICON = {
  image: Image,
  video: Video,
  document: FileText,
  audio: Headphones,
  voice: Mic,
  sticker: Sticker,
};

export function Ticks({ message, size = 16 }) {
  if (!message) return null;
  if (message._failed) return <span className="ticks ticks--failed">!</span>;
  if (message._pending || !message.id) return <ClockIcon size={size - 2} className="ticks ticks--pending" />;
  if (message.is_read) return <DoubleTick size={size} className="ticks ticks--read" />;
  if (message.is_delivered) return <DoubleTick size={size} className="ticks" />;
  return <SingleTick size={size} className="ticks" />;
}

function Preview({ room, me, senderName, typingText, preview, reacted }) {
  const message = room.lastMessage;
  if (typingText) return <span className="chat-item__typing">{typingText}</span>;
  if (reacted) return <span className="chat-item__text">{preview}</span>;
  if (!message) return <span className="chat-item__placeholder">{room.isGroup ? "Group created" : "Tap to start chatting"}</span>;

  const isOwn = Number(message.sender?.id) === Number(me?.id);
  const kind = messageKind(message);
  if (kind === "deleted") {
    return (
      <span className="chat-item__deleted">
        <Ban size={14} /> {previewText(message, me?.id)}
      </span>
    );
  }
  if (kind === "group_event") {
    // System message: the actor is the sender, no ticks / "Name:" prefix.
    return <span className="chat-item__text">{previewText(message, me?.id, () => senderName)}</span>;
  }
  if (kind === "call") {
    const summary = callSummary(parseSpecial(message.content), me?.id);
    const Icon = summary.missed ? PhoneMissed : summary.video ? Video : Phone;
    return (
      <span className={`chat-item__call ${summary.missed ? "is-missed" : ""}`}>
        <Icon size={15} /> {summary.label}
      </span>
    );
  }
  const text = preview || previewText(message, me?.id);
  if (kind === "system") {
    return (
      <span className="chat-item__system">
        <Timer size={14} /> <span className="chat-item__text">{text}</span>
      </span>
    );
  }
  const Icon = KIND_ICON[kind];
  return (
    <>
      {isOwn ? <Ticks message={message} /> : null}
      {room.isGroup && !isOwn && senderName ? <span className="chat-item__sender">{senderName}: </span> : null}
      {Icon ? <Icon size={15} className="chat-item__kind" /> : null}
      <span className="chat-item__text">{text}</span>
    </>
  );
}

function ChatListItem({
  room,
  title,
  me,
  senderName,
  preview,
  reacted,
  typingText,
  active,
  selectMode,
  selected,
  onOpen,
  onToggleSelect,
  onStartSelect,
}) {
  const [menuAnchor, setMenuAnchor] = useState(null);
  // An ongoing group call replaces the preview: "Ongoing voice call · Join".
  const activeCallType = useStore((state) => (room.isGroup ? state.activeCalls?.[room.id]?.call_type || null : null));
  const inThatCall = useStore((state) => Boolean(room.isGroup && state.currentCallId && Number(state.activeCalls?.[room.id]?.id) === Number(state.currentCallId)));
  const unread = room.unread > 0;
  const photo = room.isGroup ? room.groupPhoto : room.otherUser?.profile?.profile_picture;
  const statusGroup = useStatusGroup(room.isGroup ? null : room.otherUser?.id);

  const pressTimer = useRef(null);

  return (
    <div
      className={`chat-item ${active ? "is-active" : ""} ${selected ? "is-selected" : ""} ${menuAnchor ? "has-menu" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => (selectMode ? onToggleSelect(room.id) : onOpen(room.id))}
      onKeyDown={(event) => {
        if (event.key === "Enter") onOpen(room.id);
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        setMenuAnchor({ left: event.clientX, right: event.clientX, top: event.clientY, bottom: event.clientY });
      }}
      // Phones: press and hold opens the chat menu (iOS Safari has no contextmenu event).
      onTouchStart={(event) => {
        const touch = event.touches[0];
        window.clearTimeout(pressTimer.current);
        pressTimer.current = window.setTimeout(() => {
          setMenuAnchor({ left: touch.clientX, right: touch.clientX, top: touch.clientY, bottom: touch.clientY });
        }, 500);
      }}
      onTouchMove={() => window.clearTimeout(pressTimer.current)}
      onTouchEnd={() => window.clearTimeout(pressTimer.current)}
    >
      {selectMode ? <Checkbox checked={selected} onChange={() => onToggleSelect(room.id)} label={`Select ${title}`} /> : null}
      <span
        className="avatar-wrap"
        onClick={(event) => {
          if (selectMode) return;
          // WhatsApp: tapping the picture opens their status (ring) or the profile pop-up.
          event.stopPropagation();
          if (!(ringFor(statusGroup) && openUserStatus(room.otherUser?.id))) openProfilePeek(room, title, photo);
        }}
      >
        <Avatar src={photo} name={title} group={room.isGroup} size={49} ring={ringFor(statusGroup)} />
        {room.disappearingSeconds ? (
          <span className="avatar-timer" aria-label="Disappearing messages on" title="Disappearing messages">
            <Timer size={12} strokeWidth={2.4} />
          </span>
        ) : null}
      </span>
      <div className="chat-item__body">
        <div className="chat-item__top">
          <span className="chat-item__title">{title}</span>
          <span className={`chat-item__time ${unread && !room.isMuted ? "is-unread" : ""}`}>{listTime(room.activityAt)}</span>
        </div>
        <div className="chat-item__bottom">
          <span className="chat-item__preview">
            {activeCallType && !typingText ? (
              <span className="chat-item__ongoing">
                {activeCallType === "VIDEO" ? <Video size={15} /> : <Phone size={15} />}
                <span>Ongoing {activeCallType === "VIDEO" ? "video" : "voice"} call</span>
              </span>
            ) : (
              <Preview room={room} me={me} senderName={senderName} typingText={typingText} preview={preview} reacted={reacted} />
            )}
          </span>
          <span className="chat-item__meta">
            {activeCallType && !inThatCall && !selectMode ? (
              <button
                type="button"
                className="gcall-join gcall-join--sm"
                onClick={(event) => {
                  event.stopPropagation();
                  requestJoinCall(room.id);
                }}
                aria-label="Join call"
              >
                Join
              </button>
            ) : null}
            {room.isMuted ? <BellOff size={16} className="chat-item__icon" aria-label="Muted" /> : null}
            {room.isPinned ? <Pin size={16} className="chat-item__icon" aria-label="Pinned" /> : null}
            {room.unreadMention ? <span className="badge badge--mention" aria-label="You were mentioned">@</span> : null}
            {unread ? <span className={`badge ${room.isMuted ? "badge--muted" : ""}`}>{room.unread > 999 ? "999+" : room.unread}</span> : null}
            {!selectMode ? (
              <button
                type="button"
                className="chat-item__chevron"
                aria-label="Chat options"
                onClick={(event) => {
                  event.stopPropagation();
                  setMenuAnchor(event.currentTarget);
                }}
              >
                <ChevronDown size={20} />
              </button>
            ) : null}
          </span>
        </div>
      </div>
      {menuAnchor ? <Menu anchor={menuAnchor} items={buildRoomMenu(room, title, { onSelect: onStartSelect })} align="left" onClose={() => setMenuAnchor(null)} /> : null}
    </div>
  );
}

export default memo(ChatListItem);
