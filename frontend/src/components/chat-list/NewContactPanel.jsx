import { useEffect, useState } from "react";
import { CheckCircle2, Info, Phone, Trash2, User } from "lucide-react";
import { errorMessage } from "../../api/client";
import { contactsApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks";
import { loadContacts, openChatWith, scheduleRoomsReload } from "../../store/actions";
import { toast } from "../../services/toast";
import { formatPhone, looksLikePhone, normalizePhone } from "../../utils/phone";
import { profileName } from "../../utils/messages";
import { Avatar, PanelHeader, Spinner } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { useApp } from "../layout/AppContext";

/**
 * Create or edit a saved contact.
 *
 * A saved contact is private to the current user: a name plus a link to an
 * existing MHTalk account (found by phone number). Editing the number only
 * re-links this contact to another account — it never changes anybody's
 * account phone number.
 */
export function ContactForm({ contact, initialPhone = "", onDone, onCancel, openChatOnCreate = true }) {
  const isEdit = Boolean(contact);
  // null = not typed yet: the name then follows the person's own profile
  // name (set when they signed up), which you can keep or change.
  const [typedName, setTypedName] = useState(contact ? contact.name || "" : null);
  const [phone, setPhone] = useState(contact?.contact_user?.phone_number || initialPhone);
  const debouncedPhone = useDebouncedValue(phone, 450);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const phoneChanged = normalizePhone(phone) !== (contact?.contact_user?.phone_number || "");
  const term = debouncedPhone.trim();
  const needsLookup = looksLikePhone(term) && !(isEdit && !phoneChanged);
  const [lookupResult, setLookupResult] = useState({ term: "", state: "idle" });

  useEffect(() => {
    if (!needsLookup) return undefined;
    let cancelled = false;
    contactsApi
      .lookup(term)
      .then((data) => {
        if (cancelled) return;
        if (data.is_self) setLookupResult({ term, state: "error", message: "You can't save your own number." });
        else if (data.saved_contact && data.saved_contact.id !== contact?.id)
          setLookupResult({ term, state: "error", message: `Already saved as "${data.saved_contact.name || formatPhone(data.user.phone_number)}".` });
        else setLookupResult({ term, state: "found", data });
      })
      .catch((err) => !cancelled && setLookupResult({ term, state: "error", message: errorMessage(err, "This phone number isn't on MHTalk.") }));
    return () => {
      cancelled = true;
    };
  }, [term, needsLookup, contact]);

  let lookup;
  if (!looksLikePhone(term)) lookup = { state: "idle" };
  else if (isEdit && !phoneChanged) lookup = { state: "found", data: { user: contact.contact_user } };
  else lookup = lookupResult.term === term ? lookupResult : { state: "loading" };
  const suggestedName = !isEdit && lookup.state === "found" ? profileName(lookup.data.user) : "";
  const name = typedName ?? suggestedName;
  const setName = setTypedName;

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!name.trim()) {
      setError("Enter a name for this contact.");
      return;
    }
    if (!looksLikePhone(phone)) {
      setError("Enter the contact's phone number with country code.");
      return;
    }
    setBusy(true);
    try {
      let saved;
      if (isEdit) {
        const fields = { name: name.trim() };
        if (phoneChanged) fields.phone_number = normalizePhone(phone);
        saved = await contactsApi.update(contact.id, fields);
        toast.success("Contact updated");
      } else {
        saved = await contactsApi.create(name.trim(), normalizePhone(phone));
        toast.success("Contact saved");
      }
      await loadContacts();
      scheduleRoomsReload();
      if (!isEdit && openChatOnCreate && saved?.contact_user) {
        const roomId = await openChatWith(saved.contact_user);
        onDone?.(saved, roomId);
      } else {
        onDone?.(saved);
      }
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the contact."));
      setBusy(false);
    }
  }

  function remove() {
    confirmAction({
      title: `Delete ${contact.name}?`,
      message: "This removes the contact from your list. Your chat history stays.",
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        try {
          await contactsApi.remove(contact.id);
          await loadContacts();
          scheduleRoomsReload();
          toast("Contact deleted");
          onDone?.(null);
        } catch (err) {
          toast.error(errorMessage(err));
        }
      },
    });
  }

  const found = lookup.state === "found" ? lookup.data.user : null;

  return (
    <form className="contact-form" onSubmit={submit} noValidate>
      <div className="contact-form__avatar">
        <Avatar src={found?.profile?.profile_picture} name={name} size={96} />
      </div>
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      <div className="contact-form__field">
        <User size={20} />
        <div className="field">
          <label htmlFor="contact-name">Name</label>
          <input id="contact-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} autoFocus />
        </div>
      </div>
      <div className="contact-form__field">
        <Phone size={20} />
        <div className="field">
          <label htmlFor="contact-phone">Phone</label>
          <input id="contact-phone" type="tel" placeholder="+92 300 1234567" value={phone} onChange={(event) => setPhone(event.target.value)} />
          {lookup.state === "loading" ? <span className="field__hint"><Spinner size={12} /> Checking number…</span> : null}
          {lookup.state === "found" && found ? (
            <span className="lookup-ok">
              <CheckCircle2 size={14} /> This number is on MHTalk{profileName(found) ? ` · ~ ${profileName(found)}` : ""}
            </span>
          ) : null}
          {lookup.state === "error" ? <span className="field__error">{lookup.message}</span> : null}
        </div>
      </div>
      {isEdit ? (
        <p className="contact-form__note">
          <Info size={16} />
          <span>
            Changing the number links this saved contact to a different MHTalk account. It does not change anyone's
            account phone number. The saved name is shown in your chat list, chat header and groups.
          </span>
        </p>
      ) : (
        <p className="contact-form__note">
          <Info size={16} />
          <span>The contact must already have a MHTalk account with this number. Only you can see the name you save.</span>
        </p>
      )}
      <div className="contact-form__actions">
        {isEdit ? (
          <button type="button" className="btn btn--text danger-text" onClick={remove}>
            <Trash2 size={16} /> Delete contact
          </button>
        ) : null}
        {onCancel ? <button type="button" className="btn btn--ghost" onClick={onCancel}>Cancel</button> : null}
        <button type="submit" className="btn btn--primary" disabled={busy || lookup.state === "error"}>
          {busy ? <Spinner size={16} /> : "Save"}
        </button>
      </div>
    </form>
  );
}

export default function NewContactPanel({ contact, initialPhone }) {
  const app = useApp();
  return (
    <section className="panel">
      <PanelHeader title={contact ? "Edit contact" : "New contact"} onBack={app.popPanel} variant="sub" />
      <div className="panel__scroll">
        <ContactForm
          contact={contact}
          initialPhone={initialPhone}
          onDone={(saved, roomId) => {
            app.popPanel();
            if (roomId) app.openRoom(roomId);
          }}
        />
      </div>
    </section>
  );
}
