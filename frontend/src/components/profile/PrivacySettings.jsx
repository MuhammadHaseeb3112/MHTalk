import { useEffect, useState } from "react";
import { ChevronRight, ShieldAlert, Trash2, UserX } from "lucide-react";
import { errorMessage } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { toast } from "../../services/toast";
import { dispatch, getState, useStore } from "../../store/store";
import { detailTime } from "../../utils/format";
import { formatPhone, normalizePhone } from "../../utils/phone";
import { PanelHeader, Spinner, Toggle } from "../common/ui";

/**
 * Settings > Privacy and Settings > Account (WhatsApp layout). Privacy is
 * enforced by the server (apps/accounts/privacy.py); this is just the UI.
 */

const AUDIENCE = [
  { value: "everyone", label: "Everyone" },
  { value: "contacts", label: "My contacts" },
  { value: "nobody", label: "Nobody" },
];
const ONLINE = [
  { value: "everyone", label: "Everyone" },
  { value: "same_as_last_seen", label: "Same as last seen" },
];
const DEFAULTS = { last_seen: "everyone", online: "everyone", profile_photo: "everyone", about: "everyone", read_receipts: true };
const label = (options, value) => options.find((option) => option.value === value)?.label || "Everyone";

function RadioGroup({ name, options, value, onChange, disabled }) {
  return (
    <div className="radio-list radio-list--panel" role="radiogroup" aria-label={name}>
      {options.map((option) => (
        <label key={option.value} className={`radio ${value === option.value ? "is-checked" : ""}`}>
          <input type="radio" name={name} value={option.value} checked={value === option.value} disabled={disabled} onChange={() => onChange(option.value)} />
          <span className="radio__dot" />
          <span>{option.label}</span>
        </label>
      ))}
    </div>
  );
}

function Row({ title, subtitle, onClick, icon: Icon }) {
  return (
    <button type="button" className="settings-row" onClick={onClick}>
      {Icon ? <Icon size={22} /> : null}
      <span className="settings-row__body">
        <span className="settings-row__title">{title}</span>
        {subtitle ? <span className="settings-row__subtitle">{subtitle}</span> : null}
      </span>
      <ChevronRight size={18} className="settings-row__chevron" />
    </button>
  );
}

/** Privacy settings, kept in sync with `me.privacy` (also updated by other tabs via /me). */
function usePrivacy() {
  const fromMe = useStore((state) => state.me?.privacy);
  const [settings, setSettings] = useState(() => ({ ...DEFAULTS, ...(fromMe || {}) }));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authApi
      .privacy()
      .then((data) => !cancelled && setSettings(data))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const update = async (patch) => {
    const previous = settings;
    setSettings({ ...settings, ...patch }); // optimistic
    setSaving(true);
    try {
      const data = await authApi.updatePrivacy(patch);
      setSettings(data);
      const me = getState().me;
      if (me) dispatch({ type: "me", me: { ...me, privacy: data } });
    } catch (error) {
      setSettings(previous);
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };
  return { settings, update, saving };
}

export function PrivacyView({ onBack, blockedCount, onOpenBlocked, onOpenStatus }) {
  const { settings, update, saving } = usePrivacy();
  const [sub, setSub] = useState(null); // lastSeen | photo | about

  if (sub === "lastSeen") {
    return (
      <section className="panel">
        <PanelHeader title="Last seen and online" onBack={() => setSub(null)} variant="sub" />
        <div className="panel__scroll">
          <div className="section-label section-label--muted">Who can see my last seen</div>
          <RadioGroup name="last_seen" options={AUDIENCE} value={settings.last_seen} disabled={saving} onChange={(value) => update({ last_seen: value })} />
          <div className="section-label section-label--muted">Who can see when I'm online</div>
          <RadioGroup name="online" options={ONLINE} value={settings.online} disabled={saving} onChange={(value) => update({ online: value })} />
          <p className="info-muted info-pad">If you don't share your last seen and online, you won't be able to see other people's last seen and online.</p>
        </div>
      </section>
    );
  }
  if (sub === "photo" || sub === "about") {
    const field = sub === "photo" ? "profile_photo" : "about";
    const title = sub === "photo" ? "Profile photo" : "About";
    return (
      <section className="panel">
        <PanelHeader title={title} onBack={() => setSub(null)} variant="sub" />
        <div className="panel__scroll">
          <div className="section-label section-label--muted">Who can see my {sub === "photo" ? "profile photo" : "About"}</div>
          <RadioGroup name={field} options={AUDIENCE} value={settings[field]} disabled={saving} onChange={(value) => update({ [field]: value })} />
        </div>
      </section>
    );
  }

  const lastSeenSubtitle =
    settings.online === "everyone" && settings.last_seen !== "everyone"
      ? `${label(AUDIENCE, settings.last_seen)}, Everyone`
      : label(AUDIENCE, settings.last_seen);
  return (
    <section className="panel">
      <PanelHeader title="Privacy" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <div className="section-label section-label--muted">Who can see my personal info</div>
        <Row title="Last seen and online" subtitle={lastSeenSubtitle} onClick={() => setSub("lastSeen")} />
        <Row title="Profile photo" subtitle={label(AUDIENCE, settings.profile_photo)} onClick={() => setSub("photo")} />
        <Row title="About" subtitle={label(AUDIENCE, settings.about)} onClick={() => setSub("about")} />
        <Row title="Status" subtitle="Choose who sees your status updates" onClick={onOpenStatus} />
        <div className="settings-toggle">
          <span className="settings-row__body">
            <span className="settings-row__title">Read receipts</span>
            <span className="settings-row__subtitle settings-row__subtitle--wrap">
              If turned off, you won't send or receive Read receipts. Read receipts are always sent for group chats.
            </span>
          </span>
          <Toggle checked={Boolean(settings.read_receipts)} label="Read receipts" onChange={(value) => update({ read_receipts: value })} />
        </div>
        <div className="section-label section-label--muted">Contacts</div>
        <Row icon={UserX} title="Blocked contacts" subtitle={blockedCount ? `${blockedCount}` : "None"} onClick={onOpenBlocked} />
      </div>
    </section>
  );
}

function DeleteAccountView({ onBack }) {
  const me = useStore((state) => state.me);
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!phone.trim() || !password) {
      setError("Enter your phone number and password.");
      return;
    }
    setBusy(true);
    try {
      await authApi.deleteAccount(normalizePhone(phone), password);
      toast("Your account was deleted");
      window.dispatchEvent(new Event("whatsup:signed-out"));
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete your account."));
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <PanelHeader title="Delete this account" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <form className="delete-account" onSubmit={submit} noValidate>
          <div className="delete-account__warning">
            <ShieldAlert size={22} />
            <div>
              <p className="delete-account__title">Deleting this account will:</p>
              <ul>
                <li>Delete your account info and profile photo</li>
                <li>Delete you from all MHTalk groups</li>
                <li>Delete your status updates, contacts and blocked list</li>
                <li>Sign you out on every device</li>
              </ul>
              <p className="info-muted">People you chatted with keep their chat history; your messages appear from "Deleted account".</p>
            </div>
          </div>
          <p className="delete-account__lead">To delete your account, confirm your phone number ({formatPhone(me?.phone_number)}) and enter your password.</p>
          {error ? <div className="form-error" role="alert">{error}</div> : null}
          <div className="field">
            <label htmlFor="delete-phone">Phone number</label>
            <input id="delete-phone" type="tel" autoComplete="tel" placeholder="+92 300 1234567" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="delete-password">Password</label>
            <input id="delete-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button type="submit" className="btn btn--danger delete-account__submit" disabled={busy}>
            {busy ? <Spinner size={16} /> : "Delete account"}
          </button>
        </form>
      </div>
    </section>
  );
}

export function AccountView({ onBack }) {
  const me = useStore((state) => state.me);
  const [sub, setSub] = useState(null);
  if (sub === "delete") return <DeleteAccountView onBack={() => setSub(null)} />;
  return (
    <section className="panel">
      <PanelHeader title="Account" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <div className="account-info info-pad">
          <span className="info-label">Phone number</span>
          <p className="info-value">{formatPhone(me.phone_number)}</p>
          {me.email ? (
            <>
              <span className="info-label">Email</span>
              <p className="info-value">{me.email}</p>
            </>
          ) : null}
          <span className="info-label">Member since</span>
          <p className="info-value">{detailTime(me.date_joined)}</p>
        </div>
        <button type="button" className="settings-row is-danger" onClick={() => setSub("delete")}>
          <Trash2 size={22} />
          <span className="settings-row__body">
            <span className="settings-row__title">Delete account</span>
          </span>
        </button>
      </div>
    </section>
  );
}
