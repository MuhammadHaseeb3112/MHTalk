import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Phone, Search, Send, X } from "lucide-react";
import { messageApi } from "../../api/endpoints";
import { errorMessage } from "../../api/client";
import { toast } from "../../services/toast";
import { receiveMessage } from "../../store/actions";
import { useStore } from "../../store/store";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { Avatar, Checkbox, Modal, Spinner } from "../common/ui";

const MAX_CONTACTS = 5;

/**
 * WhatsApp flow: "Contacts to send" (search + multi-select) →
 * "Send contact" preview → each contact goes out as its own card.
 */
export default function ShareContactDialog({ room, onClose }) {
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState([]);
  const [step, setStep] = useState("pick");
  const [busy, setBusy] = useState(false);

  const people = useMemo(() => {
    const list = contacts
      .filter((contact) => contact.contact_user?.phone_number)
      .map((contact) => ({ id: `c${contact.id}`, name: contact.name || contact.contact_user.display_name, phone: contact.contact_user.phone_number, photo: contact.contact_user.profile?.profile_picture }))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (me?.phone_number) list.unshift({ id: "me", name: me.display_name || "Me", phone: me.phone_number, photo: me.profile?.profile_picture, self: true });
    const term = query.trim().toLowerCase();
    if (!term) return list;
    const digits = phoneDigits(term);
    return list.filter((person) => person.name.toLowerCase().includes(term) || (digits && phoneDigits(person.phone).includes(digits)));
  }, [contacts, me, query]);

  const isPicked = (person) => picked.some((item) => item.id === person.id);
  function toggle(person) {
    if (isPicked(person)) setPicked(picked.filter((item) => item.id !== person.id));
    else if (picked.length >= MAX_CONTACTS) toast(`You can share up to ${MAX_CONTACTS} contacts at a time.`);
    else setPicked([...picked, person]);
  }

  async function send() {
    setBusy(true);
    try {
      for (const person of picked) {
        const saved = await messageApi.send({ room: room.id, message_type: "CONTACT", content: { name: person.name, phone: person.phone } });
        receiveMessage(room.id, saved);
      }
      onClose();
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
    }
  }

  if (step === "review") {
    return (
      <Modal onClose={onClose} width={440} className="share-contact-dialog">
        <div className="share-contact__bar">
          <button type="button" className="icon-btn" aria-label="Back" onClick={() => setStep("pick")}><ArrowLeft size={22} /></button>
          <h2>{picked.length > 1 ? "Send contacts" : "Send contact"}</h2>
        </div>
        <div className="share-contact__review">
          {picked.map((person) => (
            <div key={person.id} className="share-contact__card">
              <div className="share-contact__card-head">
                <Avatar src={person.photo} name={person.name} size={48} />
                <strong>{person.name}{person.self ? " (You)" : ""}</strong>
              </div>
              <div className="share-contact__card-row">
                <Phone size={20} />
                <span>
                  {formatPhone(person.phone)}
                  <small>Mobile</small>
                </span>
              </div>
            </div>
          ))}
        </div>
        <button type="button" className="share-contact__fab" aria-label="Send" disabled={busy} onClick={send}>
          {busy ? <Spinner size={20} /> : <Send size={22} />}
        </button>
      </Modal>
    );
  }

  return (
    <Modal onClose={onClose} width={440} className="share-contact-dialog">
      <div className="share-contact__bar">
        <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><X size={22} /></button>
        <div className="share-contact__title">
          <h2 className="share-contact__title-mobile">Contacts to send</h2>
          <h2 className="share-contact__title-desktop">Send contacts</h2>
          <small>{picked.length} selected</small>
        </div>
      </div>
      <label className="share-contact__search">
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or number" aria-label="Search contacts" />
      </label>
      {picked.length ? (
        <div className="share-contact__chips">
          {picked.map((person) => (
            <button key={person.id} type="button" className="share-contact__chip" onClick={() => toggle(person)} aria-label={`Remove ${person.name}`}>
              <Avatar src={person.photo} name={person.name} size={44} />
              <span>{person.name.split(" ")[0]}</span>
              <X size={12} className="share-contact__chip-x" />
            </button>
          ))}
        </div>
      ) : null}
      <div className="share-contact__list" role="listbox" aria-multiselectable="true">
        {people.length ? (
          people.map((person, index) => (
            <div key={person.id} className="share-contact__group">
              {index === 0 && person.self ? <p className="share-contact__section">You</p> : null}
              {!person.self && (index === 0 || people[index - 1].self) ? <p className="share-contact__section">Contacts on MHTalk</p> : null}
              <button type="button" role="option" aria-selected={isPicked(person)} className="share-contact__row" onClick={() => toggle(person)}>
                <Checkbox checked={isPicked(person)} label={`Select ${person.name}`} decorative />
                <span className="share-contact__avatar">
                  <Avatar src={person.photo} name={person.name} size={46} />
                  {isPicked(person) ? <span className="share-contact__tick" aria-hidden="true">✓</span> : null}
                </span>
                <span className="share-contact__text">
                  <strong>{person.name}{person.self ? " (You)" : ""}</strong>
                  <small>{formatPhone(person.phone)}</small>
                </span>
              </button>
            </div>
          ))
        ) : (
          <p className="modal__text share-contact__empty">{query ? "No contacts found." : "You have no saved contacts to share."}</p>
        )}
      </div>
      {picked.length ? (
        <button type="button" className="share-contact__fab" aria-label="Next" onClick={() => setStep("review")}>
          <ArrowRight size={22} />
        </button>
      ) : null}
    </Modal>
  );
}
