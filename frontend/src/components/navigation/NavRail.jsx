import { memo } from "react";
import { Contact, Images, Phone, Settings, Sparkles } from "lucide-react";
import { useMediaQuery } from "../../hooks";
import { useStore } from "../../store/store";
import { Avatar } from "../common/ui";
import { ChatsIcon, StatusIcon } from "../common/Icons";

/**
 * Compact vertical navigation on desktop; on phones a WhatsApp-style bottom
 * tab bar (Chats, Updates, Calls, Contacts, You). MHTalk AI and Media move to
 * the floating button / chat menu there, so the bar keeps five roomy tabs.
 * Badges are derived from real state: unread chats (non-archived), unseen
 * statuses and unacknowledged missed calls.
 */
function NavRail({ section, onChange, onOpenMedia }) {
  const me = useStore((state) => state.me);
  const unreadChats = useStore((state) =>
    Object.values(state.rooms).filter((room) => !room.isArchived && room.unread > 0 && room.id !== state.activeRoomId).length,
  );
  const unseenStatus = useStore((state) => state.statusFeed.some((group) => Number(group.unseen_count) > 0));
  const missed = useStore((state) => state.missedUnseen);
  const compact = useMediaQuery("(max-width: 900px)");

  if (compact) {
    const tabs = [
      { id: "chats", label: "Chats", icon: (active) => <ChatsIcon filled={active} />, badge: unreadChats || null },
      { id: "status", label: "Updates", icon: (active) => <StatusIcon filled={active} />, dot: unseenStatus },
      { id: "calls", label: "Calls", icon: () => <Phone size={22} strokeWidth={1.8} />, badge: missed || null },
      { id: "contacts", label: "Contacts", icon: () => <Contact size={22} strokeWidth={1.8} /> },
      {
        id: "settings",
        label: "You",
        match: ["settings", "profile"],
        icon: () => <Avatar src={me?.profile?.profile_picture} name={me?.profile?.display_name} size={26} />,
      },
    ];
    return (
      <nav className="tabbar" aria-label="Main navigation">
        {tabs.map((tab) => {
          const active = (tab.match || [tab.id]).includes(section);
          return (
            <button
              key={tab.id}
              type="button"
              className={`tabbar__btn ${active ? "is-active" : ""}`}
              onClick={() => onChange(tab.id)}
              aria-label={tab.badge ? `${tab.label}, ${tab.badge} unread` : tab.label}
              aria-current={active ? "page" : undefined}
            >
              <span className="tabbar__pill">
                {tab.icon(active)}
                {tab.badge ? <span className="tabbar__badge">{tab.badge > 99 ? "99+" : tab.badge}</span> : null}
                {tab.dot ? <span className="tabbar__dot" aria-label="New status updates" /> : null}
              </span>
              <span className="tabbar__label">{tab.label}</span>
            </button>
          );
        })}
      </nav>
    );
  }

  const items = [
    { id: "chats", label: "Chats", icon: (active) => <ChatsIcon filled={active} />, badge: unreadChats || null },
    { id: "calls", label: "Calls", icon: () => <Phone size={22} strokeWidth={1.8} />, badge: missed || null },
    { id: "status", label: "Status", icon: (active) => <StatusIcon filled={active} />, dot: unseenStatus },
    { id: "contacts", label: "Contacts", icon: () => <Contact size={22} strokeWidth={1.8} /> },
    { id: "ai", label: "MHTalk AI", icon: () => <span className="rail__ai"><Sparkles size={18} strokeWidth={2} /></span> },
  ];

  return (
    <nav className="rail" aria-label="Main navigation">
      <div className="rail__group">
        {items.map((item) => {
          const active = section === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`rail__btn ${active ? "is-active" : ""}`}
              onClick={() => onChange(item.id)}
              aria-label={item.badge ? `${item.label}, ${item.badge} unread` : item.label}
              aria-current={active ? "page" : undefined}
              data-tooltip={item.label}
            >
              {item.icon(active)}
              {item.badge ? <span className="rail__badge">{item.badge > 99 ? "99+" : item.badge}</span> : null}
              {item.dot ? <span className="rail__dot" aria-label="New status updates" /> : null}
              <span className="rail__label">{item.label}</span>
            </button>
          );
        })}
      </div>
      <div className="rail__group rail__group--bottom">
        <button type="button" className="rail__btn rail__btn--media" onClick={onOpenMedia} aria-label="Media from all chats" data-tooltip="Media">
          <Images size={22} strokeWidth={1.8} />
          <span className="rail__label">Media</span>
        </button>
        <button
          type="button"
          className={`rail__btn ${section === "settings" ? "is-active" : ""}`}
          onClick={() => onChange("settings")}
          aria-label="Settings"
          data-tooltip="Settings"
        >
          <Settings size={22} strokeWidth={1.8} />
          <span className="rail__label">Settings</span>
        </button>
        <button
          type="button"
          className={`rail__btn rail__btn--avatar ${section === "profile" ? "is-active" : ""}`}
          onClick={() => onChange("profile")}
          aria-label="Profile"
          data-tooltip="Profile"
        >
          <Avatar src={me?.profile?.profile_picture} name={me?.profile?.display_name} size={30} />
          <span className="rail__label">You</span>
        </button>
      </div>
    </nav>
  );
}

export default memo(NavRail);
