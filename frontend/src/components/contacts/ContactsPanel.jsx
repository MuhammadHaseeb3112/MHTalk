import { useMemo, useState } from "react";
import { MessageSquare, Pencil, Share2, UserPlus, Users } from "lucide-react";
import { ForwardDialog } from "../conversation/dialogs";
import { sendContactCard } from "../conversation/shareContact";
import { errorMessage } from "../../api/client";
import { openChatWith } from "../../store/actions";
import { useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { profileName } from "../../utils/messages";
import { Avatar, EmptyState, IconButton, PanelHeader, SearchInput } from "../common/ui";
import { ContactForm } from "../chat-list/NewContactPanel";
import { groupByLetter } from "../../utils/rules";
import { useApp } from "../layout/AppContext";

/** Saved contacts: search, open chat, add, edit (re-link) and delete. */
export default function ContactsPanel() {
  const app = useApp();
  const contacts = useStore((state) => state.contacts);
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState(null); // null | { contact? }
  const [sharing, setSharing] = useState(null); // contact being shared

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const digits = phoneDigits(term);
    return [...contacts]
      .filter(
        (contact) =>
          !term ||
          String(contact.name || "").toLowerCase().includes(term) ||
          (digits.length >= 2 && phoneDigits(contact.contact_user?.phone_number).includes(digits)) ||
          String(profileName(contact.contact_user)).toLowerCase().includes(term),
      )
      .sort((a, b) => String(a.name).localeCompare(String(b.name)));
  }, [contacts, query]);

  async function open(contact) {
    try {
      const roomId = await openChatWith(contact.contact_user);
      app.openRoom(roomId);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  if (editor) {
    return (
      <section className="panel">
        <PanelHeader title={editor.contact ? "Edit contact" : "New contact"} onBack={() => setEditor(null)} variant="sub" />
        <div className="panel__scroll">
          <ContactForm
            contact={editor.contact}
            openChatOnCreate={false}
            onDone={() => setEditor(null)}
            onCancel={() => setEditor(null)}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <PanelHeader title="Contacts" actions={<IconButton icon={UserPlus} label="New contact" onClick={() => setEditor({})} />} />
      <SearchInput value={query} onChange={setQuery} placeholder="Search name or number" />
      <div className="panel__scroll">
        {!query ? (
          <div className="list-pad list-pad--top">
            <button type="button" className="row row--action" onClick={() => setEditor({})}>
              <span className="row__icon-circle"><UserPlus size={22} /></span>
              <span className="row__body"><span className="row__title">New contact</span></span>
            </button>
            <button type="button" className="row row--action" onClick={() => { app.setSection("chats"); window.setTimeout(() => app.pushPanel("newGroup"), 0); }}>
              <span className="row__icon-circle"><Users size={22} /></span>
              <span className="row__body"><span className="row__title">New group</span></span>
            </button>
          </div>
        ) : null}
        {!query && contacts.length ? <div className="section-label section-label--plain">{contacts.length} contact{contacts.length === 1 ? "" : "s"} on MHTalk</div> : null}
        {groupByLetter(filtered).map(([letter, items]) => (
          <div key={letter}>
            <div className="letter-header">{letter}</div>
            <div className="list-pad">
              {items.map((contact) => (
                <div key={contact.id} className="row contact-row" role="button" tabIndex={0} onClick={() => open(contact)} onKeyDown={(event) => event.key === "Enter" && open(contact)}>
                  <Avatar src={contact.contact_user?.profile?.profile_picture} name={contact.name} />
                  <span className="row__body">
                    <span className="row__title">{contact.name}</span>
                    <span className="row__subtitle">{contact.contact_user?.profile?.about || formatPhone(contact.contact_user?.phone_number)}</span>
                  </span>
                  <span className="contact-row__actions">
                    <IconButton icon={MessageSquare} label={`Message ${contact.name}`} onClick={(event) => { event.stopPropagation(); open(contact); }} />
                    <IconButton icon={Share2} label={`Share ${contact.name}`} onClick={(event) => { event.stopPropagation(); setSharing(contact); }} />
                    <IconButton icon={Pencil} label={`Edit ${contact.name}`} onClick={(event) => { event.stopPropagation(); setEditor({ contact }); }} />
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
        {!filtered.length ? (
          query ? (
            <EmptyState text={`No contacts match "${query}".`} />
          ) : (
            <EmptyState icon={UserPlus} title="No contacts yet" text="Save people by their MHTalk phone number to chat with them.">
              <button type="button" className="btn btn--primary" onClick={() => setEditor({})}>Add contact</button>
            </EmptyState>
          )
        ) : null}
      </div>
      {sharing ? (
        <ForwardDialog
          title={`Share ${sharing.name} to`}
          onClose={() => setSharing(null)}
          onSend={(roomIds) => sendContactCard({ name: sharing.name, phone: sharing.contact_user?.phone_number }, roomIds)}
        />
      ) : null}
    </section>
  );
}
