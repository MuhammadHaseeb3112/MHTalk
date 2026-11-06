import { useEffect, useMemo, useState } from "react";
import { useStarredCount } from "../../hooks";
import { Ban, Bell, BellOff, Eraser, Heart, HeartOff, Pencil, Phone, Star, Timer, Trash2, UserPlus, Video } from "lucide-react";
import { contactsApi } from "../../api/endpoints";
import { favoriteRoom, muteRoom } from "../../store/actions";
import { useStore } from "../../store/store";
import { lastSeenLabel } from "../../utils/format";
import { contactsByUser, disappearingLabel, profileName, roomTitle } from "../../utils/messages";
import { formatPhone } from "../../utils/phone";
import { Avatar, Modal, PanelHeader, Toggle } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { askBlock, askClearChat, askDeleteChat, askMute } from "../chat-list/roomMenu";
import { ContactForm } from "../chat-list/NewContactPanel";
import { useCalls } from "../calls/callContext";
import Lightbox from "../media/Lightbox";
import { InfoRow, MediaSummary } from "./shared";
import { DisappearingDialog } from "../conversation/FeatureDialogs";
import StatusViewer from "../status/StatusViewer";
import { ringFor, sortedGroup, useStatusGroup } from "../status/statusRing";

/** Contact info drawer (1:1 chats). */
export default function ContactInfo({ roomId }) {
  const app = useApp();
  const { startCall } = useCalls();
  const room = useStore((state) => state.rooms[roomId]);
  const me = useStore((state) => state.me);
  const starredCount = useStarredCount(roomId);
  const contacts = useStore((state) => state.contacts);
  const presence = useStore((state) => (room?.otherUser ? state.presence[room.otherUser.id] : null));
  const blocked = useStore((state) => (room?.otherUser ? state.blocked.includes(Number(room.otherUser.id)) : false));
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [groups, setGroups] = useState([]);
  const [editing, setEditing] = useState(false);
  const [viewPhoto, setViewPhoto] = useState(false);
  const [disappearingOpen, setDisappearingOpen] = useState(false);

  const user = room?.otherUser;
  const saved = user ? contactMap.get(Number(user.id)) : null;
  const statusGroup = useStatusGroup(user?.id);
  const [viewStatus, setViewStatus] = useState(false);

  useEffect(() => {
    if (!user?.id) return;
    contactsApi.commonGroups(user.id).then(setGroups).catch(() => setGroups([]));
  }, [user?.id]);

  if (!room || !user) return null;
  const title = roomTitle(room, contactMap, me);
  const about = user.profile?.about;
  const online = presence ? presence.is_online : user.profile?.is_online;
  const lastSeen = presence?.last_seen || user.profile?.last_seen;
  const photo = user.profile?.profile_picture;

  return (
    <section className="panel info-panel">
      <PanelHeader title="Contact info" onBack={app.closeDrawer} variant="close" actions={saved ? <button type="button" className="icon-btn" aria-label="Edit contact" onClick={() => setEditing(true)}><Pencil size={19} /></button> : null} />
      <div className="panel__scroll">
        <div className="info-hero">
          <Avatar
            src={photo}
            name={title}
            size={200}
            ring={ringFor(statusGroup)}
            onClick={ringFor(statusGroup) ? () => setViewStatus(true) : photo ? () => setViewPhoto(true) : undefined}
          />
          <h2>{title}</h2>
          <p className="info-hero__sub">{saved ? formatPhone(user.phone_number) : profileName(user) ? `~ ${profileName(user)}` : ""}</p>
          {!blocked ? <p className="info-hero__presence">{online ? "online" : lastSeen ? lastSeenLabel(lastSeen) : ""}</p> : null}
          <div className="info-hero__actions">
            <button type="button" onClick={() => startCall(room, "audio")} disabled={blocked}>
              <Phone size={20} /> Voice
            </button>
            <button type="button" onClick={() => startCall(room, "video")} disabled={blocked}>
              <Video size={20} /> Video
            </button>
            {!saved ? (
              <button type="button" onClick={() => setEditing(true)}>
                <UserPlus size={20} /> Add
              </button>
            ) : null}
          </div>
        </div>

        <div className="info-section">
          <span className="info-label">About</span>
          <p className="info-value">{about || "Hey there! I'm using MHTalk."}</p>
          {!saved ? (
            <>
              <span className="info-label">Phone number</span>
              <p className="info-value">{formatPhone(user.phone_number)}</p>
            </>
          ) : null}
        </div>

        <MediaSummary roomId={room.id} onOpen={() => app.openDrawer("media", { roomId: room.id })} />

        <div className="info-section info-section--list">
          <InfoRow icon={Star} title="Starred messages" onClick={() => app.pushPanel("starred", { roomId: room.id })} trailing={starredCount ? <span className="info-action__count">{starredCount}</span> : null} />
          <InfoRow
            icon={Timer}
            title="Disappearing messages"
            subtitle={disappearingLabel(room.disappearingSeconds)}
            onClick={() => setDisappearingOpen(true)}
          />
          <InfoRow
            icon={room.isMuted ? BellOff : Bell}
            title="Mute notifications"
            trailing={<Toggle checked={room.isMuted} label="Mute notifications" onChange={(value) => (value ? askMute(room) : muteRoom(room.id, "off"))} />}
          />
        </div>

        {groups.length ? (
          <div className="info-section info-section--list">
            <span className="info-label info-label--pad">{groups.length} group{groups.length > 1 ? "s" : ""} in common</span>
            {groups.map((group) => (
              <button key={group.id} type="button" className="row" onClick={() => app.openRoom(group.id)}>
                <Avatar src={group.photo} name={group.name} group size={40} />
                <span className="row__body">
                  <span className="row__title">{group.name}</span>
                  <span className="row__subtitle">{group.member_names.join(", ")}</span>
                </span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="info-section info-section--list">
          <InfoRow
            icon={room.isFavorite ? HeartOff : Heart}
            title={room.isFavorite ? "Remove from favorites" : "Add to favorites"}
            onClick={() => favoriteRoom(room.id, !room.isFavorite)}
          />
          <InfoRow icon={Ban} title={blocked ? `Unblock ${title}` : `Block ${title}`} danger onClick={() => askBlock(room, title, blocked)} />
          <InfoRow icon={Eraser} title="Clear chat" danger onClick={() => askClearChat(room)} />
          <InfoRow icon={Trash2} title="Delete chat" danger onClick={() => askDeleteChat(room, title)} />
        </div>
      </div>

      {editing ? (
        <Modal title={saved ? "Edit contact" : "Save contact"} onClose={() => setEditing(false)} width={460}>
          <ContactForm contact={saved} initialPhone={user.phone_number} openChatOnCreate={false} onDone={() => setEditing(false)} onCancel={() => setEditing(false)} />
        </Modal>
      ) : null}
      {disappearingOpen ? <DisappearingDialog room={room} onClose={() => setDisappearingOpen(false)} /> : null}
      {viewStatus && statusGroup ? <StatusViewer groups={[sortedGroup(statusGroup)]} startGroup={0} onClose={() => setViewStatus(false)} /> : null}
      {viewPhoto ? (
        <Lightbox
          items={[{ message: { id: `photo-${user.id}`, sender: user, created_at: user.profile?.updated_at || new Date().toISOString(), content: "" }, attachment: { id: "p", file: photo, mime_type: "image/jpeg", file_name: "profile.jpg" } }]}
          nameOf={() => title}
          onClose={() => setViewPhoto(false)}
        />
      ) : null}
    </section>
  );
}
