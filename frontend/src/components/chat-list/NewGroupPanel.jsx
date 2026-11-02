import { useMemo, useRef, useState } from "react";
import { ArrowRight, Camera, Check, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { useObjectUrl } from "../../hooks";
import { dispatch, useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { normalizeFiles } from "../../utils/files";
import { normalizeRoom } from "../../utils/messages";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { Avatar, Checkbox, EmptyState, PanelHeader, SearchInput, Spinner } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { groupByLetter } from "../../utils/rules";

/** Contact picker with removable chips (shared by New group & Add members). */
export function MemberPicker({ selected, onChange, exclude = [] }) {
  const contacts = useStore((state) => state.contacts);
  const [query, setQuery] = useState("");
  const excluded = useMemo(() => new Set(exclude.map(Number)), [exclude]);
  const available = useMemo(() => {
    const term = query.trim().toLowerCase();
    const digits = phoneDigits(term);
    return contacts
      .filter((contact) => !excluded.has(Number(contact.contact_user?.id)))
      .filter(
        (contact) =>
          !term ||
          String(contact.name || "").toLowerCase().includes(term) ||
          (digits.length >= 2 && phoneDigits(contact.contact_user?.phone_number).includes(digits)),
      )
      .sort((a, b) => String(a.name).localeCompare(String(b.name)));
  }, [contacts, query, excluded]);

  const selectedContacts = contacts.filter((contact) => selected.includes(Number(contact.contact_user?.id)));
  const toggle = (userId) =>
    onChange(selected.includes(userId) ? selected.filter((id) => id !== userId) : [...selected, userId]);

  return (
    <>
      {selectedContacts.length ? (
        <div className="member-chips">
          {selectedContacts.map((contact) => (
            <span key={contact.id} className="member-chip">
              <Avatar src={contact.contact_user?.profile?.profile_picture} name={contact.name} size={26} />
              <span>{contact.name}</span>
              <button type="button" aria-label={`Remove ${contact.name}`} onClick={() => toggle(Number(contact.contact_user.id))}>
                <X size={14} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <SearchInput value={query} onChange={setQuery} placeholder="Search name or number" autoFocus />
      <div className="panel__scroll">
        {available.length ? (
          groupByLetter(available).map(([letter, items]) => (
            <div key={letter}>
              <div className="letter-header">{letter}</div>
              <div className="list-pad">
                {items.map((contact) => {
                  const userId = Number(contact.contact_user?.id);
                  const checked = selected.includes(userId);
                  return (
                    <button key={contact.id} type="button" className="row" onClick={() => toggle(userId)}>
                      <Avatar src={contact.contact_user?.profile?.profile_picture} name={contact.name} />
                      <span className="row__body">
                        <span className="row__title">{contact.name}</span>
                        <span className="row__subtitle">{contact.contact_user?.profile?.about || formatPhone(contact.contact_user?.phone_number)}</span>
                      </span>
                      <Checkbox checked={checked} label={`Select ${contact.name}`} decorative />
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        ) : (
          <EmptyState text={contacts.length ? "No matching contacts." : "Save contacts first to add them to groups."} />
        )}
      </div>
    </>
  );
}

export default function NewGroupPanel() {
  const app = useApp();
  const me = useStore((state) => state.me);
  const [step, setStep] = useState(1);
  const [members, setMembers] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const photoUrl = useObjectUrl(photo);

  async function create() {
    if (!name.trim()) {
      toast.error("Enter a group name.");
      return;
    }
    setBusy(true);
    try {
      const raw = await chatApi.createGroup({ name: name.trim(), description: description.trim(), photo, participants: members });
      const room = normalizeRoom(raw, me.id);
      dispatch({ type: "rooms/upsert", room });
      app.resetPanels();
      app.openRoom(room.id);
      toast.success(`Group "${room.groupName}" created`);
    } catch (error) {
      toast.error(errorMessage(error, "Couldn't create the group."));
      setBusy(false);
    }
  }

  if (step === 1) {
    return (
      <section className="panel">
        <PanelHeader title="Add group members" onBack={app.popPanel} variant="sub" />
        <MemberPicker selected={members} onChange={setMembers} />
        <div className="panel-fab">
          <button type="button" className="fab" aria-label="Next" disabled={!members.length} onClick={() => setStep(2)}>
            <ArrowRight size={26} />
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <PanelHeader title="New group" onBack={() => setStep(1)} variant="sub" />
      <div className="panel__scroll group-setup">
        <button type="button" className="photo-picker" onClick={() => fileRef.current?.click()} aria-label="Add group icon">
          {photoUrl ? <img src={photoUrl} alt="" /> : <Camera size={30} />}
          <span>{photoUrl ? "Change" : "Add group icon"}</span>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          hidden
          onChange={async (event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            const [file] = picked ? await normalizeFiles([picked]) : [];
            if (file && !file.type.startsWith("image/")) toast.error("Choose an image file.");
            else if (file && file.size > 5 * 1024 * 1024) toast.error("Group photos must be 5 MB or smaller.");
            else if (file) setPhoto(file);
          }}
        />
        <div className="field">
          <label htmlFor="group-name">Group subject</label>
          <input id="group-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} autoFocus placeholder="Group subject (required)" />
          <span className="field__hint">{100 - name.length} characters left</span>
        </div>
        <div className="field">
          <label htmlFor="group-desc">Description (optional)</label>
          <textarea id="group-desc" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} maxLength={255} />
        </div>
        <p className="field__hint">{members.length} member{members.length === 1 ? "" : "s"} selected. You'll be the group admin.</p>
      </div>
      <div className="panel-fab">
        <button type="button" className="fab" aria-label="Create group" disabled={busy || !name.trim()} onClick={create}>
          {busy ? <Spinner size={24} className="spinner--dark" /> : <Check size={28} />}
        </button>
      </div>
    </section>
  );
}
