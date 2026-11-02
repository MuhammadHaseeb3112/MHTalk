import { useEffect, useMemo, useState } from "react";
import { Bell, ChevronRight, CircleHelp, Download, Keyboard, KeyRound, Lock, LogOut, MessageSquareText, Palette, Search, Share, SquarePlus, UserX } from "lucide-react";
import { useStore } from "../../store/store";
import { loadBlocked, setBlocked } from "../../store/actions";
import { getNotificationPrefs, requestDesktopPermission, setNotificationPrefs } from "../../services/notify";
import { toast } from "../../services/toast";
import { getInstallState, promptInstall, subscribeInstall } from "../../services/pwa";
import { disableBackgroundPush, enableBackgroundPush, pushSupported, syncBackgroundPush } from "../../services/push";
import { THEME_OPTIONS, getThemePref, setThemePref } from "../../services/theme";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { formatPhone } from "../../utils/phone";
import { Avatar, EmptyState, Modal, PanelHeader, SearchInput, Toggle } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { useApp } from "../layout/AppContext";
import { AccountView, PrivacyView } from "./PrivacySettings";

const SHORTCUTS = [
  ["New chat", "Ctrl + Alt + N"],
  ["Send message", "Enter"],
  ["New line", "Shift + Enter"],
  ["Edit last message", "↑ (empty input)"],
  ["Close menu / cancel reply", "Esc"],
  ["Next / previous photo", "→ / ←"],
  ["Pause status", "Space"],
];

function SettingRow({ icon: Icon, title, subtitle, onClick, danger }) {
  return (
    <button type="button" className={`settings-row ${danger ? "is-danger" : ""}`} onClick={onClick}>
      <Icon size={22} />
      <span className="settings-row__body">
        <span className="settings-row__title">{title}</span>
        {subtitle ? <span className="settings-row__subtitle">{subtitle}</span> : null}
      </span>
      {!danger ? <ChevronRight size={18} className="settings-row__chevron" /> : null}
    </button>
  );
}

function ToggleRow({ title, subtitle, checked, onChange, disabled }) {
  return (
    <div className={`settings-toggle ${disabled ? "is-disabled" : ""}`}>
      <span className="settings-row__body">
        <span className="settings-row__title">{title}</span>
        {subtitle ? <span className="settings-row__subtitle">{subtitle}</span> : null}
      </span>
      <Toggle checked={checked} onChange={disabled ? () => {} : onChange} label={title} />
    </div>
  );
}

function ThemeDialog({ onClose }) {
  const [value, setValue] = useState(getThemePref);
  return (
    <Modal
      title="Theme"
      onClose={onClose}
      width={400}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              setThemePref(value);
              onClose();
            }}
          >
            OK
          </button>
        </>
      }
    >
      <div className="radio-list" role="radiogroup" aria-label="Theme">
        {THEME_OPTIONS.map((option) => (
          <label key={option.value} className={`radio ${value === option.value ? "is-checked" : ""}`}>
            <input type="radio" name="theme" checked={value === option.value} onChange={() => setValue(option.value)} />
            <span className="radio__dot" />
            <span className="radio__text">
              <span>{option.label}</span>
            </span>
          </label>
        ))}
      </div>
    </Modal>
  );
}

function InstallDialog({ ios, onClose }) {
  return (
    <Modal title="Install MHTalk" onClose={onClose} width={420}>
      {ios ? (
        <ol className="install-steps">
          <li>
            Tap <Share size={18} aria-label="Share" /> <strong>Share</strong> in Safari&apos;s toolbar.
          </li>
          <li>
            Choose <SquarePlus size={18} aria-hidden="true" /> <strong>Add to Home Screen</strong>.
          </li>
          <li>Tap <strong>Add</strong>. MHTalk opens full screen from your home screen.</li>
        </ol>
      ) : (
        <ol className="install-steps">
          <li>Open your browser&apos;s menu (⋮ or the install icon in the address bar).</li>
          <li>
            Choose <strong>Install app</strong> or <strong>Add to Home screen</strong>.
          </li>
          <li>MHTalk then opens in its own window, like a native app.</li>
        </ol>
      )}
    </Modal>
  );
}

const THEME_LABELS = Object.fromEntries(THEME_OPTIONS.map((option) => [option.value, option.label]));

function BlockedView({ onBack }) {
  const blocked = useStore((state) => state.blocked);
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  useEffect(() => {
    loadBlocked();
  }, []);
  const users = blocked.map((id) => Object.values(rooms).find((room) => Number(room.otherUser?.id) === id)?.otherUser || contactMap.get(id)?.contact_user || { id, phone_number: `User #${id}` });
  return (
    <section className="panel">
      <PanelHeader title="Blocked contacts" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <p className="info-muted info-pad">Blocked contacts can no longer call you or send you messages.</p>
        {!users.length ? <EmptyState icon={UserX} text="No blocked contacts" /> : null}
        <div className="list-pad">
          {users.map((user) => (
            <div key={user.id} className="row row--static">
              <Avatar src={user.profile?.profile_picture} name={displayUserName(user, contactMap)} size={44} />
              <span className="row__body">
                <span className="row__title">{displayUserName(user, contactMap)}</span>
                <span className="row__subtitle">{formatPhone(user.phone_number)}</span>
              </span>
              <button type="button" className="btn btn--ghost" onClick={() => setBlocked(user.id, false)}>Unblock</button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/** Settings (WhatsApp Web style list). */
export default function SettingsPanel() {
  const app = useApp();
  const me = useStore((state) => state.me);
  const blockedCount = useStore((state) => state.blocked.length);
  const [view, setView] = useState("main");
  const [prefs, setPrefs] = useState(getNotificationPrefs);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState(null);
  const [themePref, setThemePrefState] = useState(getThemePref);
  const [install, setInstall] = useState(getInstallState);
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => subscribeInstall(setInstall), []);

  const update = (patch) => setPrefs(setNotificationPrefs(patch));

  const onInstall = async () => {
    if (install.installed) {
      toast("MHTalk is already installed on this device.");
      return;
    }
    if (install.canPrompt) {
      const outcome = await promptInstall();
      if (outcome === "accepted") toast.success("Installing MHTalk…");
      return;
    }
    setModal(install.ios ? "install-ios" : "install");
  };

  const onBackgroundPush = async (value) => {
    setPushBusy(true);
    try {
      if (value) {
        await enableBackgroundPush();
        toast.success("Background notifications are on.");
      } else {
        await disableBackgroundPush();
      }
      setPrefs(getNotificationPrefs());
    } catch (error) {
      toast.error(error.message);
      setPrefs(setNotificationPrefs({ backgroundPush: false }));
    } finally {
      setPushBusy(false);
    }
  };

  if (view === "blocked") return <BlockedView onBack={() => setView("privacy")} />;

  if (view === "privacy") {
    return (
      <PrivacyView
        onBack={() => setView("main")}
        blockedCount={blockedCount}
        onOpenBlocked={() => setView("blocked")}
        onOpenStatus={() => app.setSection("status")}
      />
    );
  }

  if (view === "account") return <AccountView onBack={() => setView("main")} />;

  if (view === "notifications") {
    return (
      <section className="panel">
        <PanelHeader title="Notifications" onBack={() => setView("main")} variant="sub" />
        <div className="panel__scroll">
          <ToggleRow title="Sounds" subtitle="Play a sound for incoming messages" checked={prefs.sound} onChange={(value) => update({ sound: value })} />
          <ToggleRow
            title="Desktop notifications"
            subtitle="Show notifications when MHTalk is in the background"
            checked={prefs.desktop}
            onChange={async (value) => {
              if (value) {
                const permission = await requestDesktopPermission();
                if (permission !== "granted") {
                  toast.error("Notifications are blocked by your browser for this site.");
                  return;
                }
              }
              update({ desktop: value });
            }}
          />
          <ToggleRow
            title="Background notifications"
            subtitle={pushSupported() ? "Get messages and calls even when MHTalk is closed" : "Not supported by this browser"}
            checked={Boolean(prefs.backgroundPush)}
            disabled={pushBusy || !pushSupported()}
            onChange={onBackgroundPush}
          />
          <ToggleRow
            title="Show previews"
            subtitle="Display message text in notifications"
            checked={prefs.preview}
            onChange={(value) => {
              update({ preview: value });
              syncBackgroundPush();
            }}
          />
        </div>
      </section>
    );
  }

  if (view === "chats") {
    return (
      <section className="panel">
        <PanelHeader title="Chats" onBack={() => setView("main")} variant="sub" />
        <div className="panel__scroll">
          <div className="section-label section-label--muted">Display</div>
          <SettingRow icon={Palette} title="Theme" subtitle={THEME_LABELS[themePref]} onClick={() => setModal("theme")} />
          <div className="section-label section-label--muted">Chat settings</div>
          <ToggleRow title="Enter is send" subtitle="Enter key will send your message (Shift+Enter for a new line)" checked={prefs.enterToSend} onChange={(value) => update({ enterToSend: value })} />
        </div>
        {modal === "theme" ? (
          <ThemeDialog
            onClose={() => {
              setModal(null);
              setThemePrefState(getThemePref());
            }}
          />
        ) : null}
      </section>
    );
  }

  const rows = [
    { key: "account", icon: KeyRound, title: "Account", subtitle: "Phone number, delete account", onClick: () => setView("account") },
    { key: "privacy", icon: Lock, title: "Privacy", subtitle: "Last seen, profile photo, read receipts, blocked contacts", onClick: () => setView("privacy") },
    { key: "chats", icon: MessageSquareText, title: "Chats", subtitle: "Theme, Enter is send", onClick: () => setView("chats") },
    { key: "notifications", icon: Bell, title: "Notifications", subtitle: "Message sounds, desktop alerts", onClick: () => setView("notifications") },
    !install.installed
      ? { key: "install", icon: Download, title: "Install app", subtitle: install.ios ? "Add MHTalk to your Home Screen" : "Use MHTalk like a native app", onClick: onInstall }
      : null,
    { key: "shortcuts", icon: Keyboard, title: "Keyboard shortcuts", subtitle: "Quick actions", onClick: () => setModal("shortcuts") },
    { key: "help", icon: CircleHelp, title: "Help", subtitle: "About MHTalk", onClick: () => setModal("help") },
  ].filter((row) => row && (!query || `${row.title} ${row.subtitle}`.toLowerCase().includes(query.toLowerCase())));

  return (
    <section className="panel settings-panel">
      <PanelHeader title="Settings" />
      <SearchInput value={query} onChange={setQuery} placeholder="Search settings" />
      <div className="panel__scroll">
        <button type="button" className="settings-profile" onClick={() => app.setSection("profile")}>
          <Avatar src={me.profile?.profile_picture} name={me.profile?.display_name} size={64} />
          <span className="settings-row__body">
            <span className="settings-profile__name">{me.profile?.display_name || formatPhone(me.phone_number)}</span>
            <span className="settings-row__subtitle">{me.profile?.about}</span>
          </span>
        </button>
        {rows.map((row) => (
          <SettingRow key={row.key} icon={row.icon} title={row.title} subtitle={row.subtitle} onClick={row.onClick} />
        ))}
        {!rows.length ? <EmptyState icon={Search} text="No settings found" /> : null}
        <SettingRow
          icon={LogOut}
          title="Log out"
          danger
          onClick={() => confirmAction({ title: "Log out?", message: "You can log back in with your phone number and password.", confirmLabel: "Log out", danger: true, onConfirm: app.onLogout })}
        />
      </div>

      {modal === "shortcuts" ? (
        <Modal title="Keyboard shortcuts" onClose={() => setModal(null)} width={460}>
          <div className="shortcuts">
            {SHORTCUTS.map(([label, keys]) => (
              <div key={label} className="shortcuts__row">
                <span>{label}</span>
                <kbd>{keys}</kbd>
              </div>
            ))}
          </div>
        </Modal>
      ) : null}
      {modal === "install" || modal === "install-ios" ? <InstallDialog ios={modal === "install-ios"} onClose={() => setModal(null)} /> : null}
      {modal === "help" ? (
        <Modal title="MHTalk" onClose={() => setModal(null)} width={420}>
          <p className="modal__text">
            MHTalk is a real-time messaging app built with Django Channels and React. Messages, receipts, typing, presence,
            statuses and calls sync live across all of your open tabs.
          </p>
        </Modal>
      ) : null}
    </section>
  );
}
