import { Archive, ArchiveRestore, Ban, BellOff, Bell, CheckCheck, Heart, HeartOff, Pin, PinOff, Trash2, Eraser, LogOut } from "lucide-react";
import { chatApi } from "../../api/endpoints";
import { archiveRoom, clearChat, deleteChat, favoriteRoom, markRoomRead, muteRoom, pinRoom, setBlocked, refreshRoom } from "../../store/actions";
import { getState } from "../../store/store";
import { toast } from "../../services/toast";
import { errorMessage } from "../../api/client";
import { chooseOption, confirmAction } from "../common/dialogs";

const MUTE_OPTIONS = [
  { value: "8h", label: "8 hours" },
  { value: "1w", label: "1 week" },
  { value: "always", label: "Always" },
];

export function askMute(room) {
  chooseOption({
    title: "Mute notifications",
    text: "Other members will not see that you muted this chat. You will still be notified if you are mentioned.",
    options: MUTE_OPTIONS,
    confirmLabel: "Mute",
    onChoose: (duration) => muteRoom(room.id, duration),
  });
}

export function askDeleteChat(room, title) {
  confirmAction({
    title: `Delete chat with ${title}?`,
    message: "Messages will only be removed from this device and your devices on MHTalk. The chat reappears if a new message arrives.",
    confirmLabel: "Delete chat",
    danger: true,
    onConfirm: () => deleteChat(room.id),
  });
}

export function askClearChat(room) {
  confirmAction({
    title: "Clear this chat?",
    message: "Messages will only be removed for you. The chat stays in your list.",
    confirmLabel: "Clear chat",
    danger: true,
    onConfirm: () => clearChat(room.id),
  });
}

export function askBlock(room, title, blocked) {
  const user = room.otherUser;
  if (!user) return;
  if (blocked) {
    setBlocked(user.id, false);
    return;
  }
  confirmAction({
    title: `Block ${title}?`,
    message: "Blocked contacts will no longer be able to call you or send you messages.",
    confirmLabel: "Block",
    danger: true,
    onConfirm: () => setBlocked(user.id, true),
  });
}

export function askExitGroup(room, onLeft) {
  confirmAction({
    title: `Exit "${room.groupName}"?`,
    message: "Only group admins will be notified that you left the group.",
    confirmLabel: "Exit group",
    danger: true,
    onConfirm: async () => {
      try {
        await chatApi.leaveGroup(room.id);
        await refreshRoom(room.id);
        onLeft?.();
      } catch (error) {
        toast.error(errorMessage(error));
      }
    },
  });
}

/** Items for the chat-list hover menu and right-click menu. */
export function buildRoomMenu(room, title, { onSelect } = {}) {
  const blocked = room.otherUser && getState().blocked.includes(Number(room.otherUser.id));
  return [
    room.isArchived
      ? { label: "Unarchive chat", icon: ArchiveRestore, onClick: () => archiveRoom(room.id, false) }
      : { label: "Archive chat", icon: Archive, onClick: () => archiveRoom(room.id, true) },
    room.isMuted
      ? { label: "Unmute notifications", icon: Bell, onClick: () => muteRoom(room.id, "off") }
      : { label: "Mute notifications", icon: BellOff, onClick: () => askMute(room) },
    !room.isArchived &&
      (room.isPinned
        ? { label: "Unpin chat", icon: PinOff, onClick: () => pinRoom(room.id, false) }
        : { label: "Pin chat", icon: Pin, onClick: () => pinRoom(room.id, true) }),
    room.unread > 0 ? { label: "Mark as read", icon: CheckCheck, onClick: () => markRoomRead(room.id, { immediate: true }) } : null,
    room.isFavorite
      ? { label: "Remove from favorites", icon: HeartOff, onClick: () => favoriteRoom(room.id, false) }
      : { label: "Add to favorites", icon: Heart, onClick: () => favoriteRoom(room.id, true) },
    onSelect ? { label: "Select chat", icon: CheckCheck, onClick: () => onSelect(room.id) } : null,
    { divider: true },
    !room.isGroup ? { label: blocked ? "Unblock" : "Block", icon: Ban, onClick: () => askBlock(room, title, blocked) } : null,
    room.isGroup ? { label: "Exit group", icon: LogOut, danger: true, onClick: () => askExitGroup(room) } : null,
    { label: "Clear chat", icon: Eraser, onClick: () => askClearChat(room) },
    { label: "Delete chat", icon: Trash2, danger: true, onClick: () => askDeleteChat(room, title) },
  ].filter(Boolean);
}
