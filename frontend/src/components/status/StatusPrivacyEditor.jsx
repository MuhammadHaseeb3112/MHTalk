import { useEffect, useMemo, useState } from "react";
import { statusApi } from "../../api/endpoints";
import { useStore } from "../../store/store";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { Avatar, Checkbox, EmptyState, SearchInput, Spinner } from "../common/ui";

const PRIVACY_OPTIONS = [
  { value: "CONTACTS", label: "My contacts", hint: "Share with all of your contacts" },
  { value: "CONTACTS_EXCEPT", label: "My contacts except…", hint: "Share with your contacts except people you select" },
  { value: "ONLY_SHARE_WITH", label: "Only share with…", hint: "Only share with selected contacts" },
  { value: "EVERYONE", label: "Everyone", hint: "Anyone who has a chat with you on MHTalk" },
];

/** Who can see my status updates: the radio list and the contact picker. */
export default function StatusPrivacyEditor({ value, onChange }) {
  const [people, setPeople] = useState(null);
  const [query, setQuery] = useState("");
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);

  useEffect(() => {
    statusApi.contacts().then((rows) => setPeople(rows.map((row) => row.user))).catch(() => setPeople([]));
  }, []);

  const update = onChange;
  const needsPicker = value.visibility === "CONTACTS_EXCEPT" || value.visibility === "ONLY_SHARE_WITH";
  const filtered = (people || []).filter((user) => !query || displayUserName(user, contactMap).toLowerCase().includes(query.toLowerCase()));

  return (
    <>
        <p className="section-label section-label--muted">Who can see my status updates</p>
        <div className="radio-list radio-list--panel">
          {PRIVACY_OPTIONS.map((option) => (
            <label key={option.value} className={`radio ${value.visibility === option.value ? "is-checked" : ""}`}>
              <input type="radio" name="status-privacy" checked={value.visibility === option.value} onChange={() => update({ visibility: option.value, users: option.value === value.visibility ? value.users : [] })} />
              <span className="radio__dot" />
              <span className="radio__text">
                <span>{option.label}</span>
                <small>
                  {option.value === value.visibility && needsPicker
                    ? `${value.users.length} contact${value.users.length === 1 ? "" : "s"} ${option.value === "CONTACTS_EXCEPT" ? "excluded" : "included"}`
                    : option.hint}
                </small>
              </span>
            </label>
          ))}
        </div>
        {needsPicker ? (
          <>
            <div className="section-label">{value.visibility === "CONTACTS_EXCEPT" ? "Hide status from" : "Share status with"}</div>
            <SearchInput value={query} onChange={setQuery} placeholder="Search contacts" />
            {!people ? <div className="list-loading"><Spinner /></div> : null}
            <div className="list-pad">
              {filtered.map((user) => {
                const checked = value.users.includes(Number(user.id));
                const toggle = () => update({ ...value, users: checked ? value.users.filter((id) => id !== Number(user.id)) : [...value.users, Number(user.id)] });
                return (
                  <button key={user.id} type="button" className="row" onClick={toggle}>
                    <Avatar src={user.profile?.profile_picture} name={displayUserName(user, contactMap)} size={40} />
                    <span className="row__body"><span className="row__title">{displayUserName(user, contactMap)}</span></span>
                    <Checkbox checked={checked} label={`Select ${displayUserName(user, contactMap)}`} decorative />
                  </button>
                );
              })}
              {people && !people.length ? <EmptyState text="Save contacts or start chats to choose who sees your status." /> : null}
            </div>
          </>
        ) : null}
    </>
  );
}
