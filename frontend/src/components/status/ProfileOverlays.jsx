import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Eye, Image as ImageIcon, Info, MessageSquareText, Phone, Video } from "lucide-react";
import { useApp } from "../layout/AppContext";
import { useCalls } from "../calls/callContext";
import { Avatar, Menu } from "../common/ui";
import Lightbox from "../media/Lightbox";
import StatusViewer from "./StatusViewer";
import { getOverlay, openPhoto, openUserStatus, setOverlay, subscribeOverlay } from "./profileOverlay";

function ProfilePeek({ room, title, photo, onClose }) {
  const app = useApp();
  const calls = useCalls();
  const run = (fn) => () => {
    onClose();
    fn();
  };
  const actions = [
    { label: "Message", icon: MessageSquareText, onClick: () => app.openRoom(room.id) },
    !room.isGroup && { label: "Voice call", icon: Phone, onClick: () => calls?.startCall(room, "audio") },
    !room.isGroup && { label: "Video call", icon: Video, onClick: () => calls?.startCall(room, "video") },
    {
      label: "Info",
      icon: Info,
      onClick: () => {
        app.openRoom(room.id);
        window.setTimeout(() => app.openDrawer(room.isGroup ? "group" : "contact", { roomId: room.id }), 50);
      },
    },
  ].filter(Boolean);
  return createPortal(
    <div className="profile-peek__backdrop" onClick={onClose} role="presentation">
      <div className="profile-peek" role="dialog" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <button type="button" className="profile-peek__photo" onClick={photo ? run(() => openPhoto(title, photo)) : undefined} aria-label="View profile picture">
          {photo ? <Avatar src={photo} name={title} size={280} className="profile-peek__img" /> : <Avatar name={title} group={room.isGroup} size={280} className="profile-peek__img" />}
          <span className="profile-peek__name">{title}</span>
        </button>
        <div className="profile-peek__actions">
          {actions.map((action) => (
            <button key={action.label} type="button" aria-label={action.label} onClick={run(action.onClick)}>
              <action.icon size={22} />
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function ProfileOverlays() {
  const current = useSyncExternalStore(subscribeOverlay, getOverlay);
  if (!current) return null;
  const close = () => setOverlay(null);
  switch (current.type) {
    case "status":
      return <StatusViewer groups={[current.group]} startGroup={0} onClose={close} />;
    case "peek":
      return <ProfilePeek room={current.room} title={current.title} photo={current.photo} onClose={close} />;
    case "photo":
      return (
        <Lightbox
          items={[{ message: { id: `peek-${current.title}`, sender: { display_name: current.title }, created_at: new Date(0).toISOString(), content: "" }, attachment: { id: "p", file: current.photo, mime_type: "image/jpeg", file_name: "profile.jpg" } }]}
          nameOf={() => current.title}
          onClose={close}
        />
      );
    case "menu":
      return (
        <Menu
          anchor={current.anchor}
          align="left"
          onClose={close}
          items={[
            current.photo && { label: "View profile picture", icon: ImageIcon, onClick: () => openPhoto(current.title, current.photo) },
            { label: "View status", icon: Eye, onClick: () => openUserStatus(current.userId) },
            current.onInfo && { label: "Contact info", icon: Info, onClick: current.onInfo },
          ].filter(Boolean)}
        />
      );
    default:
      return null;
  }
}
