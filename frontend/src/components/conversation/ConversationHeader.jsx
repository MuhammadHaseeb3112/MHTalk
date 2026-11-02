import { memo, useMemo } from "react";
import {
  Archive,
  ArchiveRestore,
  ArrowLeft,
  Ban,
  Bell,
  BellOff,
  CheckSquare,
  Eraser,
  Heart,
  HeartOff,
  Info,
  LogOut,
  MoreVertical,
  Phone,
  Pin,
  PinOff,
  Search,
  Star,
  Timer,
  Trash2,
  Video,
  XCircle,
} from "lucide-react";
import { useTicker } from "../../hooks";
import { archiveRoom, favoriteRoom, muteRoom, pinRoom } from "../../store/actions";
import { useStore } from "../../store/store";
import { lastSeenLabel } from "../../utils/format";
import { contactsByUser, disappearingLabel, displayUserName } from "../../utils/messages";
import { Avatar, IconButton, MenuButton } from "../common/ui";
import { requestJoinCall } from "../calls/groupCall";
import { askBlock, askClearChat, askDeleteChat, askExitGroup, askMute } from "../chat-list/roomMenu";
import { typingLabel } from "../chat-list/useChatList";

function ConversationHeader({ room, title, onOpenInfo, onSearch, onSelect, onClose, onCall, onStarred, compact }) {
  useTicker(60000);
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const typing = useStore((state) => state.typing[room.id]);
  const presence = useStore((state) => (room.otherUser ? state.presence[room.otherUser.id] : null));
  const blocked = useStore((state) => (room.otherUser ? state.blocked.includes(Number(room.otherUser.id)) : false));
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const isMember = !room.isGroup || room.participants.some((p) => Number(p.user?.id) === Number(me.id));
  // A group call is going on that I'm not in: "Join" replaces the call buttons.
  const groupCallActive = useStore((state) => {
    const active = room.isGroup ? state.activeCalls?.[room.id] : null;
    return Boolean(active && Number(active.id) !== Number(state.currentCallId));
  });
  const canCall = room.isGroup ? isMember : Boolean(room.otherUser) && !room.otherUser.is_deleted && !blocked;

  let subtitle = typingLabel(room, typing, contactMap, me);
  let subtitleClass = subtitle ? "is-typing" : "";
  if (!subtitle) {
    if (room.isGroup) {
      const names = room.participants
        .map((p) => p.user)
        .filter(Boolean)
        .map((user) => (Number(user.id) === Number(me.id) ? "You" : displayUserName(user, contactMap)))
        .sort((a, b) => (a === "You" ? 1 : b === "You" ? -1 : a.localeCompare(b)));
      subtitle = isMember ? names.join(", ") : "You're no longer a participant";
    } else if (room.otherUser) {
      const online = presence ? presence.is_online : room.otherUser.profile?.is_online;
      const lastSeen = presence?.last_seen || room.otherUser.profile?.last_seen;
      subtitle = blocked ? "Blocked" : online ? "online" : lastSeen ? lastSeenLabel(lastSeen) : "";
    }
  }
  if (!subtitle && !room.otherUser?.is_deleted) subtitle = "click here for contact info";
  if (!subtitleClass && subtitle === "online") subtitleClass = "is-online";

  const menu = [
    { label: room.isGroup ? "Group info" : "Contact info", icon: Info, onClick: onOpenInfo },
    { label: "Search", icon: Search, onClick: onSearch },
    { label: "Select messages", icon: CheckSquare, onClick: onSelect },
    { label: "Starred messages", icon: Star, onClick: onStarred },
    isMember
      ? {
          label: "Disappearing messages",
          icon: Timer,
          hint: room.disappearingSeconds ? disappearingLabel(room.disappearingSeconds) : undefined,
          onClick: () => window.dispatchEvent(new CustomEvent("whatsup:disappearing", { detail: room.id })),
        }
      : null,
    room.isMuted
      ? { label: "Unmute notifications", icon: Bell, onClick: () => muteRoom(room.id, "off") }
      : { label: "Mute notifications", icon: BellOff, onClick: () => askMute(room) },
    room.isFavorite
      ? { label: "Remove from favorites", icon: HeartOff, onClick: () => favoriteRoom(room.id, false) }
      : { label: "Add to favorites", icon: Heart, onClick: () => favoriteRoom(room.id, true) },
    !room.isArchived && (room.isPinned ? { label: "Unpin chat", icon: PinOff, onClick: () => pinRoom(room.id, false) } : { label: "Pin chat", icon: Pin, onClick: () => pinRoom(room.id, true) }),
    room.isArchived
      ? { label: "Unarchive chat", icon: ArchiveRestore, onClick: () => archiveRoom(room.id, false) }
      : { label: "Archive chat", icon: Archive, onClick: () => archiveRoom(room.id, true) },
    { label: "Close chat", icon: XCircle, onClick: onClose },
    { divider: true },
    !room.isGroup ? { label: blocked ? "Unblock" : "Block", icon: Ban, onClick: () => askBlock(room, title, blocked) } : null,
    { label: "Clear chat", icon: Eraser, danger: true, onClick: () => askClearChat(room) },
    room.isGroup && isMember ? { label: "Exit group", icon: LogOut, danger: true, onClick: () => askExitGroup(room) } : null,
    { label: "Delete chat", icon: Trash2, danger: true, onClick: () => askDeleteChat(room, title) },
  ].filter(Boolean);

  const photo = room.isGroup ? room.groupPhoto : room.otherUser?.profile?.profile_picture;

  return (
    <header className="conv-header">
      {compact ? <IconButton icon={ArrowLeft} label="Back to chats" onClick={onClose} /> : null}
      <button type="button" className="conv-header__who" onClick={onOpenInfo} aria-label={`${title} info`}>
        <span className="avatar-wrap">
          <Avatar src={photo} name={title} group={room.isGroup} size={40} />
          {room.disappearingSeconds ? (
            <span className="avatar-timer avatar-timer--sm" title={`Disappearing messages: ${disappearingLabel(room.disappearingSeconds)}`}>
              <Timer size={10} strokeWidth={2.6} />
            </span>
          ) : null}
        </span>
        <span className="conv-header__text">
          <span className="conv-header__title">{title}</span>
          <span className={`conv-header__subtitle ${subtitleClass}`}>{subtitle}</span>
        </span>
      </button>
      <div className="conv-header__actions">
        {canCall && groupCallActive ? (
          <button type="button" className="gcall-join" onClick={() => requestJoinCall(room.id)} aria-label="Join call">
            Join
          </button>
        ) : canCall ? (
          <div className="call-buttons">
            <button type="button" className="call-buttons__btn" onClick={() => onCall("video")} aria-label="Video call" data-tooltip="Video call">
              <Video size={20} />
            </button>
            <button type="button" className="call-buttons__btn" onClick={() => onCall("audio")} aria-label="Voice call" data-tooltip="Voice call">
              <Phone size={19} />
            </button>
          </div>
        ) : null}
        <IconButton icon={Search} label="Search" onClick={onSearch} />
        <MenuButton icon={MoreVertical} label="Menu" items={menu} />
      </div>
    </header>
  );
}

export default memo(ConversationHeader);
