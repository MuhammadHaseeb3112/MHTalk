import { ArrowLeft, Copy, MessageSquareText, Phone, UserPlus, Video } from "lucide-react";
import { useStore } from "../../store/store";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { Avatar, Modal } from "../common/ui";

const lastTen = (value) => phoneDigits(value).slice(-10);

/** WhatsApp "View contact": picture, name and the number with Message / Call / Video. */
export default function ViewContactDialog({ card, isMe, saved, onMessage, onCall, onAdd, onCopy, onClose }) {
  const key = lastTen(card.phone);
  const photo = useStore((state) => {
    const user =
      state.contacts.find((contact) => lastTen(contact.contact_user?.phone_number) === key)?.contact_user ||
      Object.values(state.rooms).find((room) => !room.isGroup && lastTen(room.otherUser?.phone_number) === key)?.otherUser ||
      (lastTen(state.me?.phone_number) === key ? state.me : null);
    return user?.profile?.profile_picture || "";
  });
  const name = card.name || formatPhone(card.phone);
  const run = (fn) => () => {
    onClose();
    fn();
  };
  return (
    <Modal onClose={onClose} width={420} className="view-contact-dialog">
      <div className="share-contact__bar">
        <button type="button" className="icon-btn" aria-label="Back" onClick={onClose}><ArrowLeft size={22} /></button>
        <h2>View contact</h2>
      </div>
      <div className="view-contact__head">
        <Avatar src={photo} name={name} size={56} />
        <strong>{name}{isMe ? " (You)" : ""}</strong>
      </div>
      <div className="view-contact__row">
        {isMe ? <span className="view-contact__lead" /> : (
          <button type="button" className="view-contact__icon" aria-label={`Message ${name}`} onClick={run(onMessage)}>
            <MessageSquareText size={22} />
          </button>
        )}
        <span className="view-contact__number">
          {formatPhone(card.phone)}
          <small>Mobile</small>
        </span>
        {isMe ? null : (
          <>
            <button type="button" className="view-contact__icon" aria-label="Voice call" onClick={run(() => onCall("audio"))}><Phone size={22} /></button>
            <button type="button" className="view-contact__icon" aria-label="Video call" onClick={run(() => onCall("video"))}><Video size={22} /></button>
          </>
        )}
      </div>
      <div className="view-contact__actions">
        {saved ? null : (
          <button type="button" onClick={run(onAdd)}><UserPlus size={20} /> Add to contacts</button>
        )}
        <button type="button" onClick={run(onCopy)}><Copy size={20} /> Copy number</button>
      </div>
    </Modal>
  );
}
