import { useCallback, useEffect, useMemo, useState } from "react";
import { jumpToMessage } from "../../services/jump";
import { Archive, CheckCheck, CheckSquare, Images, LogOut, MessageSquareDashed, MoreVertical, Sparkles, Star, Users, UserPlus, X } from "lucide-react";
import { messageApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks";
import { archiveRooms, deleteChat, markAllRead, markRoomRead, openChatWith } from "../../store/actions";
import { useStore } from "../../store/store";
import { listTime } from "../../utils/format";
import { contactsByUser, displayUserName, roomTitle } from "../../utils/messages";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { Avatar, EmptyState, IconButton, MenuButton, PanelHeader, SearchInput, Spinner } from "../common/ui";
import { NewChatIcon } from "../common/Icons";
import { confirmAction } from "../common/dialogs";
import { useApp } from "../layout/AppContext";
import ChatListItem from "./ChatListItem";
import { useChatList } from "./useChatList";
import { askDeleteChat } from "./roomMenu";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "favorites", label: "Favorites" },
  { id: "groups", label: "Groups" },
];

function highlight(text, query) {
  const value = String(text || "");
  const needle = query.trim();
  if (!needle) return value;
  const index = value.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return value;
  return (
    <>
      {value.slice(0, index)}
      <mark className="hl">{value.slice(index, index + needle.length)}</mark>
      {value.slice(index + needle.length)}
    </>
  );
}

export default function ChatListPanel() {
  const app = useApp();
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState([]);
  const debounced = useDebouncedValue(query, 300);
  const rows = useChatList({ filter, query: debounced });
  const me = useStore((state) => state.me);
  const roomsLoaded = useStore((state) => state.roomsLoaded);
  const activeRoomId = useStore((state) => state.activeRoomId);
  const connection = useStore((state) => state.connection);
  const archivedSummary = useStore((state) => {
    const archived = Object.values(state.rooms).filter((room) => room.isArchived);
    // Number of archived chats with unread messages (not the total message count).
    return { total: archived.length, unreadChats: archived.filter((room) => room.unread > 0 && room.id !== state.activeRoomId).length };
  });
  const unreadCount = useStore((state) => Object.values(state.rooms).filter((room) => !room.isArchived && room.unread > 0).length);
  const contacts = useStore((state) => state.contacts);
  const rooms = useStore((state) => state.rooms);

  // Server-side message search, keyed by the term it answers.
  const term = debounced.trim();
  const [hitResult, setHitResult] = useState({ term: "", hits: [] });
  useEffect(() => {
    if (term.length < 2) return undefined;
    let cancelled = false;
    messageApi
      .searchAll(term)
      .then((hits) => !cancelled && setHitResult({ term, hits }))
      .catch(() => !cancelled && setHitResult({ term, hits: [] }));
    return () => {
      cancelled = true;
    };
  }, [term]);
  const messageHits = term.length >= 2 && hitResult.term === term ? hitResult.hits : [];
  const searching = term.length >= 2 && hitResult.term !== term;

  // Saved contacts without a chat that match the search.
  const contactHits = useMemo(() => {
    const term = debounced.trim().toLowerCase();
    if (!term) return [];
    const digits = phoneDigits(term);
    const withChat = new Set(Object.values(rooms).filter((room) => !room.isGroup && room.lastMessage).map((room) => Number(room.otherUser?.id)));
    return contacts.filter((contact) => {
      if (withChat.has(Number(contact.contact_user?.id))) return false;
      return (
        String(contact.name || "").toLowerCase().includes(term) ||
        (digits.length >= 3 && phoneDigits(contact.contact_user?.phone_number).includes(digits))
      );
    });
  }, [debounced, contacts, rooms]);

  const toggleSelect = useCallback((roomId) => {
    setSelected((current) => (current.includes(roomId) ? current.filter((id) => id !== roomId) : [...current, roomId]));
  }, []);
  const startSelect = useCallback((roomId) => {
    setSelectMode(true);
    setSelected(roomId ? [roomId] : []);
  }, []);
  const exitSelect = () => {
    setSelectMode(false);
    setSelected([]);
  };

  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const searchingActive = Boolean(debounced.trim());

  const menuItems = [
    { label: "New group", icon: Users, onClick: () => app.pushPanel("newGroup") },
    ...(app.compact
      ? [
          { label: "Media from all chats", icon: Images, onClick: () => app.openMedia() },
          { label: "MHTalk AI", icon: Sparkles, onClick: () => app.setSection("ai") },
        ]
      : []),
    { label: "New contact", icon: UserPlus, onClick: () => app.pushPanel("newContact") },
    { label: "Starred messages", icon: Star, onClick: () => app.pushPanel("starred") },
    { label: "Select chats", icon: CheckSquare, onClick: () => startSelect() },
    { label: "Mark all as read", icon: CheckCheck, onClick: markAllRead, disabled: !unreadCount },
    { divider: true },
    {
      label: "Log out",
      icon: LogOut,
      danger: true,
      onClick: () => confirmAction({ title: "Log out?", message: "You can log back in with your phone number and password.", confirmLabel: "Log out", danger: true, onConfirm: app.onLogout }),
    },
  ];

  return (
    <section className="panel chat-list">
      {selectMode ? (
        <header className="panel-header panel-header--sub select-bar">
          <IconButton icon={X} label="Cancel selection" onClick={exitSelect} />
          <div className="panel-header__title">
            <h1>{selected.length} selected</h1>
          </div>
          <div className="panel-header__actions">
            <IconButton
              icon={CheckCheck}
              label="Mark as read"
              disabled={!selected.length}
              onClick={() => {
                selected.forEach((id) => markRoomRead(id, { immediate: true }));
                exitSelect();
              }}
            />
            <IconButton
              icon={Archive}
              label="Archive"
              disabled={!selected.length}
              onClick={() => {
                archiveRooms(selected, true);
                exitSelect();
              }}
            />
            <IconButton
              icon={MessageSquareDashed}
              label="Delete chats"
              disabled={!selected.length}
              onClick={() => {
                const target = selected.map((id) => rooms[id]).filter(Boolean);
                if (target.length === 1) askDeleteChat(target[0], roomTitle(target[0], contactMap, me));
                else
                  confirmAction({
                    title: `Delete ${target.length} chats?`,
                    message: "Messages will be removed only for you.",
                    confirmLabel: "Delete chats",
                    danger: true,
                    onConfirm: async () => {
                      for (const room of target) await deleteChat(room.id);
                    },
                  });
                exitSelect();
              }}
            />
          </div>
        </header>
      ) : (
        <PanelHeader
          title="MHTalk"
          actions={
            <>
              {!app.compact ? <IconButton icon={NewChatIcon} label="New chat" onClick={() => app.pushPanel("newChat")} /> : null}
              <MenuButton icon={MoreVertical} label="Menu" items={menuItems} />
            </>
          }
        />
      )}

      {connection === "offline" ? (
        <div className="connection-banner" role="status">
          <span className="connection-banner__dot" /> Connecting… Messages will sync automatically.
        </div>
      ) : null}

      <SearchInput value={query} onChange={setQuery} placeholder="Search or start a new chat" loading={searching} />

      {!searchingActive ? (
        <div className="chips" role="tablist" aria-label="Chat filters">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={filter === item.id}
              className={`chip ${filter === item.id ? "is-active" : ""}`}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
              {item.id === "unread" && unreadCount ? <span className="chip__count">{unreadCount}</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      <div className="panel__scroll">
        {!searchingActive && filter === "all" && archivedSummary.total > 0 ? (
          <button type="button" className="archived-row" onClick={() => app.pushPanel("archived")}>
            <span className="archived-row__icon">
              <Archive size={20} />
            </span>
            <span className="archived-row__label">Archived</span>
            {archivedSummary.unreadChats > 0 ? <span className="archived-row__count">{archivedSummary.unreadChats}</span> : null}
          </button>
        ) : null}

        {!roomsLoaded ? (
          <div className="list-loading">
            <Spinner />
          </div>
        ) : null}

        {searchingActive && rows.length ? <div className="section-label">Chats</div> : null}
        <div className="list-pad">
          {rows.map(({ room, title, senderName, preview, reacted, typingText }) => (
            <ChatListItem
              key={room.id}
              room={room}
              title={title}
              me={me}
              senderName={senderName}
              preview={preview}
              reacted={reacted}
              typingText={typingText}
              active={room.id === activeRoomId}
              selectMode={selectMode}
              selected={selected.includes(room.id)}
              onOpen={app.openRoom}
              onToggleSelect={toggleSelect}
              onStartSelect={startSelect}
            />
          ))}
        </div>

        {searchingActive && contactHits.length ? (
          <>
            <div className="section-label">Contacts</div>
            <div className="list-pad">
              {contactHits.map((contact) => (
                <button
                  key={contact.id}
                  type="button"
                  className="row"
                  onClick={async () => {
                    const roomId = await openChatWith(contact.contact_user);
                    app.openRoom(roomId);
                    setQuery("");
                  }}
                >
                  <Avatar src={contact.contact_user?.profile?.profile_picture} name={contact.name} />
                  <span className="row__body">
                    <span className="row__title">{highlight(contact.name, debounced)}</span>
                    <span className="row__subtitle">{formatPhone(contact.contact_user?.phone_number)}</span>
                  </span>
                </button>
              ))}
            </div>
          </>
        ) : null}

        {searchingActive && messageHits.length ? (
          <>
            <div className="section-label">Messages</div>
            <div className="list-pad">
              {messageHits.map((hit) => {
                const room = rooms[hit.room_id];
                if (!room) return null;
                const sender = room.participants.find((p) => Number(p.user?.id) === Number(hit.sender_id))?.user;
                return (
                  <button
                    key={hit.id}
                    type="button"
                    className="row row--message-hit"
                    onClick={() => {
                      app.openRoom(room.id);
                      jumpToMessage(room.id, hit.id);
                    }}
                  >
                    <span className="row__body">
                      <span className="row__title">
                        {roomTitle(room, contactMap, me)}
                        <span className="row__time">{listTime(hit.created_at)}</span>
                      </span>
                      <span className="row__subtitle">
                        {room.isGroup && sender ? `${displayUserName(sender, contactMap, { me })}: ` : ""}
                        {highlight(hit.content, debounced)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        ) : null}

        {roomsLoaded && !rows.length && !contactHits.length && !messageHits.length ? (
          searchingActive ? (
            <EmptyState title="No results" text={`No chats, contacts or messages found for "${debounced}".`} />
          ) : filter === "unread" ? (
            <EmptyState title="No unread chats" text="You're all caught up." />
          ) : filter === "favorites" ? (
            <EmptyState title="No favorites yet" text="Add chats to Favorites from the chat menu to find them quickly." />
          ) : filter === "groups" ? (
            <EmptyState title="No groups yet" text="Create a group to chat with several people at once.">
              <button type="button" className="btn btn--primary" onClick={() => app.pushPanel("newGroup")}>New group</button>
            </EmptyState>
          ) : (
            <EmptyState title="No chats yet" text="Start a conversation with one of your contacts.">
              <button type="button" className="btn btn--primary" onClick={() => app.pushPanel("newChat")}>Start a chat</button>
            </EmptyState>
          )
        ) : null}
      </div>

      {app.compact && !selectMode ? (
        <div className="fab-stack">
          <button type="button" className="fab-pill" onClick={() => app.setSection("ai")} aria-label="Ask MHTalk AI">
            <span className="fab-pill__icon"><Sparkles size={16} strokeWidth={2.2} /></span>
            Ask MHTalk AI
          </button>
          <button type="button" className="fab" onClick={() => app.pushPanel("newChat")} aria-label="New chat">
            <NewChatIcon size={24} />
          </button>
        </div>
      ) : null}
    </section>
  );
}
