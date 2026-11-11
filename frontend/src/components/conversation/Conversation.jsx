import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, Download, Forward, Heart, Info, MoreVertical, Pencil, Pin, PinOff, Reply, Smile, Star, StarOff, Trash2, CheckSquare, X } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { contactsApi } from "../../api/endpoints";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { callUser } from "../calls/callUser";
import { useMediaQuery } from "../../hooks";
import { toast } from "../../services/toast";
import { applyMessagePatch, openChatWith, reactTo, retryMessage, sendFile, toggleStar, togglePinMessage, votePoll } from "../../store/actions";
import { getState, useStore } from "../../store/store";
import { attachmentKind, contactsByUser, displayUserName, groupAbilities, isSavedContact, messageKind, profileName, roomTitle, canOpenViewOnceHere } from "../../utils/messages";
import { askBlock } from "../chat-list/roomMenu";
import { IconButton, Menu } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { useCalls } from "../calls/callContext";
import GroupCallBanner from "../calls/GroupCallBanner";
import CameraCapture from "../media/CameraCapture";
import Lightbox from "../media/Lightbox";
import MediaComposer from "../media/MediaComposer";
import { normalizeFiles, openFilePicker, validateFiles } from "../../utils/files";
import { rememberSticker } from "../../utils/stickers";
import { canDeleteForEveryone, canEdit } from "../../utils/rules";
import Composer from "./Composer";
import ConversationHeader from "./ConversationHeader";
import MessageList from "./MessageList";
import PinnedBar from "./PinnedBar";
import ReactionPicker from "./ReactionPicker";
import { DeleteMessagesDialog, ForwardDialog, ReactionsDialog } from "./dialogs";
import { confirmAction } from "../common/dialogs";
import ViewContactDialog from "./ViewContactDialog";
import { DisappearingDialog, PollVotesDialog, ViewOncePhoneOnly, ViewOnceViewer } from "./FeatureDialogs";
import StatusViewer from "../status/StatusViewer";

/**
 * The open chat: header, message history, composer and every
 * message-level interaction (menus, reactions, selection, media).
 */
export default function Conversation({ roomId }) {
  const app = useApp();
  const calls = useCalls();
  const room = useStore((state) => state.rooms[roomId]);
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const blocked = useStore((state) => (room?.otherUser ? state.blocked.includes(Number(room.otherUser.id)) : false));
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const unknownSender = Boolean(
    room && !room.isGroup && room.otherUser && !room.otherUser.is_deleted && Number(room.otherUser.id) !== Number(me.id) && !isSavedContact(room.otherUser, contactMap),
  );
  const compact = useMediaQuery("(max-width: 900px)");

  const [initialUnread] = useState(() => room?.unread || 0);
  const [replyTo, setReplyTo] = useState(null);
  const [editing, setEditing] = useState(null);
  const [selectMode, setSelectMode] = useState(false);
  const [pressSelect, setPressSelect] = useState(false); // selection started by press-and-hold
  const [selectedIds, setSelectedIds] = useState([]);
  const [menu, setMenu] = useState(null); // { anchor, message }
  const [reacting, setReacting] = useState(null); // { anchor, message }
  const [dialog, setDialog] = useState(null); // { type, messages | message }
  const [composerFiles, setComposerFiles] = useState(null); // { files, mode }
  const [camera, setCamera] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { items, index }
  const [viewOnce, setViewOnce] = useState(null); // message being viewed once
  const [statusView, setStatusView] = useState(null); // { groups, statusId } from a status reaction card
  const [disappearingOpen, setDisappearingOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);

  const title = room ? roomTitle(room, contactMap, me) : "";
  const isMember = room && (!room.isGroup || room.participants.some((p) => Number(p.user?.id) === Number(me.id)));
  let composerDisabledReason = "";
  if (room && !isMember) composerDisabledReason = "You can't send messages to this group because you're no longer a participant.";
  else if (room?.isGroup && !groupAbilities(room, me.id).canSend) composerDisabledReason = "Only admins can send messages";
  else if (room && !room.isGroup && (room.otherUser === null || room.otherUser?.is_deleted)) composerDisabledReason = "This account no longer exists.";

  const nameOf = useCallback(
    (userId) => {
      if (Number(userId) === Number(me.id)) return "You";
      const user = room?.participants.find((p) => Number(p.user?.id) === Number(userId))?.user;
      return user ? displayUserName(user, contactMap) : "Unknown";
    },
    [room?.participants, contactMap, me.id],
  );
  const userOf = useCallback(
    (userId) => (Number(userId) === Number(me.id) ? me : room?.participants.find((p) => Number(p.user?.id) === Number(userId))?.user || null),
    [room?.participants, me],
  );

  // Header menu / contact & group info open the timer dialog through this event.
  useEffect(() => {
    const handler = (event) => Number(event.detail) === Number(roomId) && setDisappearingOpen(true);
    window.addEventListener("mhtalk:disappearing", handler);
    return () => window.removeEventListener("mhtalk:disappearing", handler);
  }, [roomId]);

  const messagesFor = useCallback(() => getState().messages[roomId]?.items || [], [roomId]);

  const openInfo = useCallback(() => app.openDrawer(room?.isGroup ? "group" : "contact", { roomId }), [app, room?.isGroup, roomId]);

  // Arrow-up in an empty composer edits your last message (like WhatsApp Web).
  useEffect(() => {
    const handler = () => {
      const last = [...messagesFor()].reverse().find((message) => canEdit(message, me.id));
      if (last) setEditing(last);
    };
    window.addEventListener("mhtalk:edit-last", handler);
    return () => window.removeEventListener("mhtalk:edit-last", handler);
  }, [messagesFor, me.id]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      if (selectMode) {
        setSelectMode(false);
        setSelectedIds([]);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectMode]);

  const pickFiles = useCallback(async (picked, mode) => {
    const files = await normalizeFiles(picked);
    // Photos saved without an extension don't show in the "Photos & videos"
    // picker, so people find them through "Document". Treat those as photos.
    const recovered = picked.every((file, index) => !file.type && files[index].type);
    if (mode === "document" && recovered && files.every((file) => /^(image|video)\//.test(file.type))) mode = "media";
    const accepted = validateFiles(files, mode === "media" ? "media" : mode === "audio" ? "audio" : "any");
    if (accepted.length) setComposerFiles({ files: accepted, mode });
  }, []);

  const sendComposerItems = useCallback(
    (items) => {
      const reply = replyTo;
      setComposerFiles(null);
      setReplyTo(null);
      items.forEach((item, index) => sendFile(roomId, item.file, { caption: item.caption, viewOnce: item.viewOnce, trim: item.trim, replyTo: index === 0 ? reply : undefined }));
    },
    [roomId, replyTo],
  );

  const openMedia = useCallback(
    (message) => {
      const items = [];
      messagesFor().forEach((item) => {
        // View once media never joins the gallery (it has no URL anyway).
        if (item.is_deleted || item.is_view_once) return;
        (item.attachments || []).forEach((attachment) => {
          const kind = attachmentKind(attachment);
          if (kind === "image" || kind === "video") items.push({ message: item, attachment });
        });
      });
      const index = Math.max(0, items.findIndex((item) => item.message === message || (message.id && item.message.id === message.id)));
      setLightbox({ items, index });
    },
    [messagesFor],
  );

  // Shared contact card: Message / Voice call / Video call / Add to contacts.
  const [viewContact, setViewContact] = useState(null);
  const handleContactCard = useCallback(
    (message, payload) => {
      const card = typeof message.content === "object" && message.content ? message.content : {};
      const phone = card.phone;
      if (!phone) return;
      const resolve = async () => {
        try {
          const found = await contactsApi.lookup(phone);
          if (found?.is_self) return found.user;
          if (!found?.user) throw new Error("missing");
          return found.user;
        } catch {
          toast.error(`${card.name || phone} isn't on MHTalk.`);
          return null;
        }
      };
      const openChat = async () => {
        const user = await resolve();
        if (!user) return;
        try {
          app.openRoom(await openChatWith(user));
        } catch (error) {
          toast.error(errorMessage(error));
        }
      };
      const isMe = phoneDigits(getState().me?.phone_number).slice(-10) === phoneDigits(phone).slice(-10);
      if (payload?.action === "message") {
        if (isMe) toast("This is your own number.");
        else openChat();
        return;
      }
      if (payload?.action === "add") {
        app.pushPanel("newContact", { initialPhone: phone, initialName: card.name });
        return;
      }
      const saved = isMe || (getState().contacts || []).some((contact) => phoneDigits(contact.contact_user?.phone_number).slice(-10) === phoneDigits(phone).slice(-10));
      setViewContact({
        card,
        isMe,
        saved,
        onMessage: openChat,
        onCall: async (type) => {
          const user = await resolve();
          if (user) callUser(user, type, calls.startCall);
        },
        onAdd: () => app.pushPanel("newContact", { initialPhone: phone, initialName: card.name }),
        onCopy: () => navigator.clipboard?.writeText(formatPhone(phone)).then(() => toast("Number copied")),
      });
    },
    [app, calls],
  );

  const handleAction = useCallback(
    (type, message, payload) => {
      switch (type) {
        case "menu": {
          const anchor = payload?.currentTarget && payload.type === "click" ? payload.currentTarget : { left: payload.clientX, right: payload.clientX, top: payload.clientY, bottom: payload.clientY };
          setMenu({ anchor, message });
          // Like WhatsApp: the reaction bar shows above the message with the menu.
          const bubble = (payload?.currentTarget || payload?.target)?.closest?.(".bubble");
          if (bubble && message.id && isMember && !message.is_deleted) setReacting({ anchor: bubble, message });
          break;
        }
        case "pressReact":
          // First stage of press-and-hold: just the reaction bar.
          if (message.id && isMember && !message.is_deleted) setReacting({ anchor: payload.anchorEl, message, fromPress: true });
          break;
        case "longPress":
          if (!message.id) return;
          setPressSelect(true);
          setSelectMode(true);
          setSelectedIds([message.id]);
          if (isMember && !message.is_deleted) setReacting({ anchor: payload.anchorEl, message, fromPress: true });
          break;
        case "react":
          setReacting({ anchor: payload.currentTarget, message });
          break;
        case "reactions":
          setDialog({ type: "reactions", message });
          break;
        case "reply":
          setEditing(null);
          setReplyTo(message);
          break;
        case "forward":
          setDialog({ type: "forward", messages: [message] });
          break;
        case "openMedia":
          openMedia(message);
          break;
        case "retry":
          retryMessage(roomId, message);
          break;
        case "toggleSelect": {
          if (!message.id) return;
          const next = selectedIds.includes(message.id) ? selectedIds.filter((id) => id !== message.id) : [...selectedIds, message.id];
          setSelectedIds(next);
          if (next.length !== 1) setReacting(null);
          // Unselecting the last message ends a press-and-hold selection (WhatsApp).
          if (!next.length && pressSelect) {
            setPressSelect(false);
            setSelectMode(false);
          }
          break;
        }
        case "call": {
          // Tapping a call card asks first, and calls back the same way
          // (voice for a voice call, video for a video call), like WhatsApp.
          const video = payload.type === "video";
          confirmAction({
            title: `${video ? "Video" : "Voice"} call ${title}?`,
            message: room?.isGroup ? "Everyone in the group will be called." : "",
            confirmLabel: video ? "Video call" : "Call",
            onConfirm: () => calls.startCall(room, payload.type),
          });
          break;
        }
        case "contact":
          handleContactCard(message, payload);
          break;
        case "vote":
          if (!isMember) toast.error("You can't vote in a group you left.");
          else votePoll(roomId, message, payload.optionId);
          break;
        case "pollVotes":
          setDialog({ type: "pollVotes", message });
          break;
        case "viewOnce":
          if (canOpenViewOnceHere()) setViewOnce(message);
          else setDialog({ type: "viewOncePhone", message });
          break;
        case "openStatus": {
          // A reaction card points at a status: open it like WhatsApp does.
          const statusId = Number(payload?.status_id);
          const state = getState();
          const ownGroup = { user: state.me, statuses: state.myStatuses };
          const group = [ownGroup, ...state.statusFeed].find((item) => item.statuses?.some((status) => Number(status.id) === statusId));
          if (!group) {
            toast("This status is no longer available.");
            break;
          }
          const statuses = [...group.statuses].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
          setStatusView({ groups: [{ ...group, statuses }], statusId });
          break;
        }
        case "disappearing":
          setDisappearingOpen(true);
          break;
        case "mention": {
          const user = getState().rooms[roomId]?.participants.find((p) => Number(p.user?.id) === Number(payload.userId))?.user;
          if (!user || Number(user.id) === Number(me.id)) return;
          openChatWith(user).then((id) => app.openRoom(id)).catch((error) => toast.error(errorMessage(error)));
          break;
        }
        default:
          break;
      }
    },
    [openMedia, roomId, calls, room, handleContactCard, isMember, me.id, app, selectedIds, pressSelect, title],
  );

  function messageMenuItems(message) {
    const kind = messageKind(message);
    const isOwn = Number(message.sender?.id) === Number(me.id);
    const viewOnceMessage = kind === "view_once";
    const attachment = viewOnceMessage ? null : message.attachments?.[0];
    const text = kind === "text" || ((kind === "image" || kind === "video") && message.content) ? message.content : "";
    // View once: no copy / download / forward / star / pin (like WhatsApp).
    return [
      isOwn && message.id ? { label: "Message info", icon: Info, onClick: () => app.openDrawer("messageInfo", { roomId, messageId: message.id }) } : null,
      isMember ? { label: "Reply", icon: Reply, onClick: () => handleAction("reply", message) } : null,
      text
        ? {
            label: "Copy",
            icon: Copy,
            onClick: () =>
              navigator.clipboard?.writeText(text).then(
                () => toast("Message copied"),
                () => toast.error("Couldn't copy."),
              ),
          }
        : null,
      isMember ? { label: "React", icon: Smile, onClick: () => setReacting({ anchor: menu?.anchor, message }) } : null,
      attachment || message.voice_note
        ? {
            label: "Download",
            icon: Download,
            onClick: () => {
              const link = document.createElement("a");
              link.href = mediaUrl(attachment?.file || message.voice_note?.audio);
              link.download = attachment?.file_name || "voice-message";
              link.target = "_blank";
              link.rel = "noopener";
              link.click();
            },
          }
        : null,
      message.message_type === "STICKER" && attachment
        ? {
            label: "Add to my stickers",
            icon: Heart,
            onClick: async () => {
              try {
                const blob = await fetch(mediaUrl(attachment.file)).then((response) => response.blob());
                await rememberSticker(new File([blob], attachment.file_name || "sticker.webp", { type: blob.type || "image/webp" }));
                toast("Added to your stickers");
              } catch {
                toast.error("Couldn't save this sticker.");
              }
            },
          }
        : null,
      kind !== "call" && !viewOnceMessage ? { label: "Forward", icon: Forward, onClick: () => setDialog({ type: "forward", messages: [message] }) } : null,
      isMember && !viewOnceMessage ? (message.is_pinned ? { label: "Unpin", icon: PinOff, onClick: () => togglePinMessage(roomId, message) } : { label: "Pin", icon: Pin, onClick: () => togglePinMessage(roomId, message) }) : null,
      viewOnceMessage ? null : message.is_starred ? { label: "Unstar", icon: StarOff, onClick: () => toggleStar(roomId, [message], false) } : { label: "Star", icon: Star, onClick: () => toggleStar(roomId, [message], true) },
      canEdit(message, me.id) ? { label: "Edit", icon: Pencil, onClick: () => { setReplyTo(null); setEditing(message); } } : null,
      { label: "Select", icon: CheckSquare, onClick: () => { setSelectMode(true); setSelectedIds([message.id]); } },
      { divider: true },
      { label: "Delete", icon: Trash2, danger: true, onClick: () => setDialog({ type: "delete", messages: [message] }) },
    ].filter(Boolean);
  }

  if (!room) return null;

  const selectedMessages = messagesFor().filter((message) => selectedIds.includes(message.id));
  const forwardable = selectedMessages.filter((message) => !message.is_view_once);
  const starrable = forwardable;

  const selectionBar = selectMode ? (
        <div className={`selection-bar ${compact ? "selection-bar--top" : ""}`}>
          <IconButton icon={X} label="Cancel selection" onClick={() => { setSelectMode(false); setSelectedIds([]); }} />
          <span className="selection-bar__count">{selectedIds.length} selected</span>
          <div className="selection-bar__actions">
            {selectedMessages.length === 1 && isMember && !selectedMessages[0].is_deleted ? (
              <IconButton icon={Reply} label="Reply" onClick={() => { handleAction("reply", selectedMessages[0]); setSelectMode(false); setSelectedIds([]); }} />
            ) : null}
            <IconButton icon={Star} label="Star" disabled={!starrable.length} onClick={() => toggleStar(roomId, starrable, !starrable.every((m) => m.is_starred))} />
            <IconButton icon={Copy} label="Copy" disabled={!selectedIds.length} onClick={() => {
              const text = selectedMessages.filter((m) => m.content && typeof m.content === "string" && !m.content.startsWith("__MHTALK_")).map((m) => m.content).join("\n");
              if (text) navigator.clipboard?.writeText(text).then(() => toast("Copied"));
            }} />
            <IconButton icon={Forward} label="Forward" disabled={!forwardable.length || forwardable.length !== selectedMessages.length} onClick={() => setDialog({ type: "forward", messages: forwardable })} />
            <IconButton icon={Trash2} label={canDeleteForEveryone(selectedMessages, me.id) ? "Delete" : "Delete for me"} disabled={!selectedIds.length} onClick={() => setDialog({ type: "delete", messages: selectedMessages })} />
            {selectedMessages.length === 1 ? (
              <IconButton icon={MoreVertical} label="More" onClick={(event) => setMenu({ anchor: event.currentTarget, message: selectedMessages[0], fromSelection: true })} />
            ) : null}
          </div>
        </div>
  ) : null;

  return (
    <section
      className={`conversation ${composerFiles || camera ? "has-media-composer" : ""}`}
      onDragEnter={(event) => {
        if (!event.dataTransfer?.types?.includes("Files")) return;
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (!dragDepth.current) setDragging(false);
      }}
      onDragOver={(event) => event.dataTransfer?.types?.includes("Files") && event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        const files = [...(event.dataTransfer?.files || [])];
        if (!files.length) return;
        normalizeFiles(files).then((typed) => {
          const allMedia = typed.every((file) => /^(image|video)\//.test(file.type));
          pickFiles(typed, allMedia ? "media" : "document");
        });
      }}
    >
      {selectMode && compact ? selectionBar : null}
      <ConversationHeader
        hidden={selectMode && compact}
        room={room}
        title={title}
        compact={compact}
        onOpenInfo={openInfo}
        onSearch={() => app.openDrawer("search", { roomId })}
        onSelect={() => { setPressSelect(false); setSelectMode(true); }}
        onStarred={() => app.pushPanel("starred", { roomId })}
        onClose={app.closeRoom}
        onCall={(type) => calls.startCall(room, type)}
      />

      <GroupCallBanner room={room} />
      <PinnedBar room={room} me={me} canPin={isMember && !blocked} />

      <div className="conversation__body">
        {unknownSender ? (
          <div className="unknown-banner" role="region" aria-label="Unknown number">
            <div className="unknown-banner__text">
              {profileName(room.otherUser) ? <strong>~ {profileName(room.otherUser)}</strong> : null}
              <span>Not a contact</span>
            </div>
            <div className="unknown-banner__actions">
              <button type="button" className="btn btn--outline-danger" onClick={() => askBlock(room, title, blocked)}>
                {blocked ? "Unblock" : "Block"}
              </button>
              <button
                type="button"
                className="btn btn--outline"
                onClick={() => app.pushPanel("newContact", { initialPhone: room.otherUser.phone_number })}
              >
                Add to contacts
              </button>
            </div>
          </div>
        ) : null}
        <MessageList
          room={room}
          me={me}
          contactMap={contactMap}
          selectMode={selectMode}
          selectedIds={selectedIds}
          onAction={handleAction}
          initialUnread={initialUnread}
        />
        {composerFiles ? (
          <MediaComposer initialFiles={composerFiles.files} mode={composerFiles.mode} title={title} onSend={sendComposerItems} onClose={() => setComposerFiles(null)} />
        ) : null}
        <input
          id="conv-camera-gallery"
          type="file"
          accept="image/*,video/*"
          multiple
          hidden
          onChange={(event) => {
            const files = [...(event.target.files || [])];
            event.target.value = "";
            if (files.length) pickFiles(files.slice(0, 30), "media");
          }}
        />
        {camera ? (
          <CameraCapture
            onClose={() => setCamera(false)}
            onGallery={() => {
              setCamera(false);
              openFilePicker("conv-camera-gallery");
            }}
            onCapture={(file) => {
              setCamera(false);
              setComposerFiles({ files: [file], mode: "media" });
            }}
          />
        ) : null}
        {dragging ? (
          <div className="drop-zone">
            <div>Drop files to send to {title}</div>
          </div>
        ) : null}
      </div>

      {selectMode && !compact ? (
        selectionBar
      ) : (
        <Composer
          key={roomId}
          room={room}
          replyTo={replyTo}
          editing={editing}
          nameOf={nameOf}
          blocked={blocked}
          disabledReason={composerDisabledReason}
          onClearReply={() => setReplyTo(null)}
          onClearEdit={() => setEditing(null)}
          onPickFiles={pickFiles}
          onOpenCamera={() => setCamera(true)}
        />
      )}

      {viewContact ? <ViewContactDialog {...viewContact} onClose={() => setViewContact(null)} /> : null}
      {menu ? <Menu anchor={menu.anchor} items={messageMenuItems(menu.message)} onClose={() => setMenu(null)} align={Number(menu.message.sender?.id) === Number(me.id) ? "right" : "left"} /> : null}
      {reacting ? (
        <ReactionPicker
          anchor={reacting.anchor}
          current={(reacting.message.reactions || []).find((r) => Number(r.user_id) === Number(me.id))?.emoji}
          onPick={(emoji) => {
            reactTo(roomId, reacting.message, emoji);
            setMenu(null);
            if (reacting.fromPress) {
              setSelectMode(false);
              setSelectedIds([]);
            }
          }}
          onClose={() => setReacting(null)}
        />
      ) : null}
      {dialog?.type === "delete" ? (
        <DeleteMessagesDialog roomId={roomId} messages={dialog.messages} myId={me.id} onClose={() => setDialog(null)} onDone={() => { setSelectMode(false); setSelectedIds([]); }} />
      ) : null}
      {dialog?.type === "forward" ? (
        <ForwardDialog messages={dialog.messages.filter((m) => m.id)} onClose={() => setDialog(null)} onDone={() => { setSelectMode(false); setSelectedIds([]); }} />
      ) : null}
      {dialog?.type === "reactions" ? (
        <ReactionsDialog
          message={messagesFor().find((m) => m.id === dialog.message.id) || dialog.message}
          room={room}
          onClose={() => setDialog(null)}
          onRemoveMine={() => {
            const mine = (dialog.message.reactions || []).find((r) => Number(r.user_id) === Number(me.id));
            if (mine) reactTo(roomId, dialog.message, mine.emoji);
          }}
        />
      ) : null}
      {dialog?.type === "viewOncePhone" ? <ViewOncePhoneOnly onClose={() => setDialog(null)} /> : null}
      {dialog?.type === "pollVotes" ? (
        <PollVotesDialog
          message={messagesFor().find((m) => m.id === dialog.message.id) || dialog.message}
          nameOf={nameOf}
          userOf={userOf}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {disappearingOpen ? <DisappearingDialog room={room} canEdit={!room.isGroup || groupAbilities(room, me.id).canEditInfo} onClose={() => setDisappearingOpen(false)} /> : null}
      {statusView ? <StatusViewer groups={statusView.groups} startStatusId={statusView.statusId} onClose={() => setStatusView(null)} /> : null}
      {viewOnce ? (
        <ViewOnceViewer
          message={viewOnce}
          nameOf={nameOf}
          onOpened={() => {
            const current = messagesFor().find((m) => m.id === viewOnce.id) || viewOnce;
            const opened = [...new Set([...(current.view_once_opened_by || []).map(Number), Number(me.id)])];
            applyMessagePatch(roomId, viewOnce.id, { view_once_opened_by: opened });
          }}
          onClose={() => setViewOnce(null)}
        />
      ) : null}
      {lightbox ? (
        <Lightbox
          items={lightbox.items}
          startIndex={lightbox.index}
          nameOf={nameOf}
          onClose={() => setLightbox(null)}
          onForward={(message) => setDialog({ type: "forward", messages: [message] })}
          onGoTo={(message) => window.dispatchEvent(new CustomEvent("mhtalk:jump-to", { detail: message.id }))}
        />
      ) : null}
    </section>
  );
}
