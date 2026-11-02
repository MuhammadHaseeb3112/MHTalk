import { useMemo, useState } from "react";
import { Send } from "lucide-react";
import { deleteMessages, forwardMessages } from "../../store/actions";
import { useStore } from "../../store/store";
import { contactsByUser, displayUserName, roomTitle, sortRooms, groupAbilities } from "../../utils/messages";
import { Avatar, Checkbox, Modal, SearchInput, Spinner } from "../common/ui";
import { canDeleteForEveryone } from "../../utils/rules";

/** WhatsApp delete dialog: "Delete for everyone" only when allowed. */
export function DeleteMessagesDialog({ roomId, messages, myId, onClose, onDone }) {
  const [busy, setBusy] = useState(null);
  const everyone = canDeleteForEveryone(messages, myId);
  const run = async (mode) => {
    setBusy(mode);
    const ok = await deleteMessages(roomId, messages, mode);
    setBusy(null);
    if (ok) {
      onDone?.();
      onClose();
    }
  };
  return (
    <Modal title={messages.length > 1 ? `Delete ${messages.length} messages?` : "Delete message?"} onClose={busy ? undefined : onClose} width={420}>
      <div className="modal__options">
        {everyone ? (
          <button type="button" className="btn btn--ghost" onClick={() => run("everyone")} disabled={Boolean(busy)}>
            {busy === "everyone" ? <Spinner size={16} /> : "Delete for everyone"}
          </button>
        ) : null}
        <button type="button" className="btn btn--ghost" onClick={() => run("me")} disabled={Boolean(busy)}>
          {busy === "me" ? <Spinner size={16} /> : "Delete for me"}
        </button>
        <button type="button" className="btn btn--text" onClick={onClose} disabled={Boolean(busy)}>
          Cancel
        </button>
      </div>
    </Modal>
  );
}

/** Pick up to 5 chats and forward the selected messages. */
export function ForwardDialog({ messages, onClose, onDone }) {
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const list = useMemo(() => {
    const term = query.trim().toLowerCase();
    return sortRooms(Object.values(rooms).filter((room) => (room.isGroup ? groupAbilities(room, me.id).canSend : room.otherUser && !room.otherUser.is_deleted)))
      .map((room) => ({ room, title: roomTitle(room, contactMap, me) }))
      .filter(({ title }) => !term || title.toLowerCase().includes(term));
  }, [rooms, contactMap, me, query]);

  const toggle = (id) =>
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : current.length >= 5 ? current : [...current, id]));

  async function send() {
    setBusy(true);
    await forwardMessages(messages, selected);
    setBusy(false);
    onDone?.();
    onClose();
  }

  return (
    <Modal title="Forward message to" onClose={busy ? undefined : onClose} width={460} className="forward-dialog">
      <SearchInput value={query} onChange={setQuery} placeholder="Search" autoFocus />
      <div className="forward-dialog__list">
        {list.map(({ room, title }) => (
          <button key={room.id} type="button" className="row" onClick={() => toggle(room.id)}>
            <Checkbox checked={selected.includes(room.id)} label={`Select ${title}`} decorative />
            <Avatar src={room.isGroup ? room.groupPhoto : room.otherUser?.profile?.profile_picture} name={title} group={room.isGroup} size={40} />
            <span className="row__body">
              <span className="row__title">{title}</span>
              {room.isGroup ? <span className="row__subtitle">{room.participants.length} members</span> : null}
            </span>
          </button>
        ))}
      </div>
      <div className="forward-dialog__footer">
        <span>{selected.length ? `${selected.length} selected${selected.length >= 5 ? " (max)" : ""}` : "Select up to 5 chats"}</span>
        <button type="button" className="fab fab--small" disabled={!selected.length || busy} onClick={send} aria-label="Forward">
          {busy ? <Spinner size={18} className="spinner--dark" /> : <Send size={20} />}
        </button>
      </div>
    </Modal>
  );
}

/** Who reacted with what. */
export function ReactionsDialog({ message, room, onClose, onRemoveMine }) {
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const userFor = (id) => room.participants.find((p) => Number(p.user?.id) === Number(id))?.user || { id, phone_number: "" };
  return (
    <Modal title={`${message.reactions.length} reaction${message.reactions.length === 1 ? "" : "s"}`} onClose={onClose} width={380}>
      <div className="list-plain">
        {message.reactions.map((reaction) => {
          const user = userFor(reaction.user_id);
          const mine = Number(reaction.user_id) === Number(me.id);
          return (
            <button key={reaction.user_id} type="button" className="row" onClick={mine ? () => { onRemoveMine(); onClose(); } : undefined}>
              <Avatar src={user.profile?.profile_picture} name={displayUserName(user, contactMap, { me })} size={40} />
              <span className="row__body">
                <span className="row__title">{displayUserName(user, contactMap, { me })}</span>
                {mine ? <span className="row__subtitle">Click to remove</span> : null}
              </span>
              <span className="emoji reaction-big">{reaction.emoji}</span>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
