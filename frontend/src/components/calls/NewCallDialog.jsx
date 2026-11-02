import { useState } from "react";
import { Phone, Video } from "lucide-react";
import { errorMessage } from "../../api/client";
import { contactsApi } from "../../api/endpoints";
import { useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { looksLikePhone, phoneDigits } from "../../utils/phone";
import { Avatar, EmptyState, IconButton, Modal, SearchInput, Spinner } from "../common/ui";
import { useCalls } from "./callContext";
import { callUser } from "./callUser";

/** Contact picker used by "New call" / "Start call". */
export default function NewCallDialog({ onClose }) {
  const contacts = useStore((state) => state.contacts);
  const rooms = useStore((state) => state.rooms);
  const me = useStore((state) => state.me);
  const { startCall } = useCalls();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const term = query.trim().toLowerCase();
  const list = contacts
    .filter((contact) => !term || contact.name?.toLowerCase().includes(term) || (phoneDigits(term).length >= 2 && phoneDigits(contact.contact_user?.phone_number).includes(phoneDigits(term))))
    .sort((a, b) => String(a.name).localeCompare(String(b.name)));
  // Groups I'm in (group voice / video calls, up to 8 people at once).
  const groups = Object.values(rooms)
    .filter((room) => room.isGroup && room.participants.some((p) => Number(p.user?.id) === Number(me.id)))
    .filter((room) => !term || String(room.groupName || "").toLowerCase().includes(term))
    .sort((a, b) => String(a.groupName).localeCompare(String(b.groupName)));

  async function callNumber() {
    setBusy(true);
    try {
      const found = await contactsApi.lookup(query);
      if (found.is_self) throw new Error("You can't call yourself.");
      onClose();
      await callUser(found.user, "audio", startCall);
    } catch (error) {
      toast.error(error?.response ? errorMessage(error) : error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="New call" onClose={onClose} width={440} className="new-call">
      <SearchInput value={query} onChange={setQuery} placeholder="Search name or number" autoFocus />
      <div className="new-call__list">
        {looksLikePhone(query) && !list.length ? (
          <button type="button" className="row" onClick={callNumber} disabled={busy}>
            <span className="row__icon-circle">{busy ? <Spinner size={18} className="spinner--dark" /> : <Phone size={20} />}</span>
            <span className="row__body"><span className="row__title">Call {query}</span></span>
          </button>
        ) : null}
        {groups.length ? <div className="section-label section-label--plain">Groups</div> : null}
        {groups.map((room) => (
          <div key={`g${room.id}`} className="row row--static">
            <Avatar src={room.groupPhoto} name={room.groupName} size={44} group />
            <span className="row__body">
              <span className="row__title">{room.groupName}</span>
              <span className="row__subtitle">{room.participants.length} members</span>
            </span>
            <IconButton icon={Video} label={`Video call ${room.groupName}`} onClick={() => { onClose(); startCall(room, "video"); }} />
            <IconButton icon={Phone} label={`Voice call ${room.groupName}`} onClick={() => { onClose(); startCall(room, "audio"); }} />
          </div>
        ))}
        {groups.length && list.length ? <div className="section-label section-label--plain">Contacts</div> : null}
        {list.map((contact) => (
          <div key={contact.id} className="row row--static">
            <Avatar src={contact.contact_user?.profile?.profile_picture} name={contact.name} size={44} />
            <span className="row__body">
              <span className="row__title">{contact.name}</span>
              <span className="row__subtitle">{contact.contact_user?.profile?.about}</span>
            </span>
            <IconButton icon={Video} label={`Video call ${contact.name}`} onClick={() => { onClose(); callUser(contact.contact_user, "video", startCall); }} />
            <IconButton icon={Phone} label={`Voice call ${contact.name}`} onClick={() => { onClose(); callUser(contact.contact_user, "audio", startCall); }} />
          </div>
        ))}
        {!list.length && !groups.length && !looksLikePhone(query) ? <EmptyState text="No contacts found." /> : null}
      </div>
    </Modal>
  );
}
