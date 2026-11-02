import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, FileText, Link2, Play, Search, X } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { jumpToMessage } from "../../services/jump";
import { useStore } from "../../store/store";
import { fileSize, listTime } from "../../utils/format";
import { contactsByUser, displayUserName, roomTitle } from "../../utils/messages";
import { EmptyState, IconButton, Spinner } from "../common/ui";
import Lightbox from "./Lightbox";

const TABS = [
  { id: "media", label: "Media" },
  { id: "docs", label: "Docs" },
  { id: "links", label: "Links" },
];

/** WhatsApp Web's "Media from all chats" window (gallery button in the side rail). */
export default function AllMediaDialog({ onClose, onOpenRoom }) {
  const me = useStore((state) => state.me);
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [tab, setTab] = useState("media");
  const [data, setData] = useState({});
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [viewer, setViewer] = useState(null);

  useEffect(() => {
    if (data[tab]) return undefined;
    let cancelled = false;
    chatApi
      .allMedia(tab)
      .then((result) => !cancelled && setData((current) => ({ ...current, [tab]: result.results || [] })))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [tab, data]);

  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && viewer === null && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, viewer]);

  const chatName = (roomId) => {
    const room = rooms[roomId];
    return room ? roomTitle(room, contactMap, me) : "Chat";
  };
  const senderOf = (item) => {
    const room = rooms[item.room_id];
    return room?.participants.find((p) => Number(p.user?.id) === Number(item.sender_id))?.user || { id: item.sender_id };
  };
  const nameOf = (userId) => {
    if (Number(userId) === Number(me.id)) return "You";
    for (const room of Object.values(rooms)) {
      const user = room.participants.find((p) => Number(p.user?.id) === Number(userId))?.user;
      if (user) return displayUserName(user, contactMap, { me });
    }
    return "Unknown";
  };

  const term = query.trim().toLowerCase();
  const items = (data[tab] || []).filter((item) => {
    if (!term) return true;
    const haystack = [chatName(item.room_id), item.file_name, item.caption, item.url, item.text].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(term);
  });
  const loading = !data[tab] && !error;

  const goTo = (item) => {
    onClose();
    onOpenRoom(item.room_id);
    jumpToMessage(item.room_id, item.message_id);
  };

  if (viewer !== null && tab === "media" && items[viewer]) {
    return (
      <Lightbox
        items={items.map((item) => ({
          message: { id: item.message_id, room_id: item.room_id, sender: senderOf(item), created_at: item.created_at, content: item.caption },
          attachment: item,
        }))}
        startIndex={viewer}
        nameOf={nameOf}
        onClose={() => setViewer(null)}
        onGoTo={(message) => goTo({ room_id: message.room_id, message_id: message.id })}
      />
    );
  }

  return createPortal(
    <div className="modal-backdrop all-media" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="all-media__window" role="dialog" aria-label="Media from all chats">
        <header className="all-media__head">
          <div className="all-media__title">
            <strong>Media</strong>
            <span>Media from all chats</span>
          </div>
          <div className="tabs all-media__tabs" role="tablist">
            {TABS.map((item) => (
              <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "is-active" : ""} onClick={() => setTab(item.id)}>
                {item.label}
              </button>
            ))}
          </div>
          <div className="all-media__actions">
            {searching ? (
              <input className="all-media__search" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by chat or file name" />
            ) : null}
            <IconButton icon={Search} label="Search" onClick={() => { setSearching((value) => !value); setQuery(""); }} />
            <IconButton icon={X} label="Close" onClick={onClose} />
          </div>
        </header>

        <div className="all-media__body">
          {loading ? <div className="list-loading"><Spinner /></div> : null}
          {error ? <EmptyState text={error} /> : null}
          {!loading && !error && !items.length ? <EmptyState text={term ? "Nothing matches your search" : `No ${tab === "media" ? "media" : tab} in your chats yet`} /> : null}

          {tab === "media" && items.length ? (
            <div className="all-media__grid">
              {items.map((item, index) => (
                <button key={item.id} type="button" className="all-media__tile" onClick={() => setViewer(index)} title={chatName(item.room_id)}>
                  {item.mime_type?.startsWith("video/") ? (
                    <>
                      <video src={`${mediaUrl(item.file)}#t=0.1`} muted preload="metadata" />
                      <span className="media-thumb__play"><Play size={18} fill="currentColor" /></span>
                    </>
                  ) : (
                    <img src={mediaUrl(item.file)} alt="" loading="lazy" />
                  )}
                  <span className="all-media__label">{chatName(item.room_id)}</span>
                </button>
              ))}
            </div>
          ) : null}

          {tab === "docs" && items.length ? (
            <div className="list-pad">
              {items.map((item) => (
                <div key={item.id} className="row doc-row">
                  <span className="doc__icon"><FileText size={20} /></span>
                  <button type="button" className="row__body all-media__open" onClick={() => goTo(item)}>
                    <span className="row__title">{item.file_name}</span>
                    <span className="row__subtitle">{fileSize(item.file_size)} · {chatName(item.room_id)} · {listTime(item.created_at)}</span>
                  </button>
                  <a className="icon-btn" href={mediaUrl(item.file)} download={item.file_name} target="_blank" rel="noopener noreferrer" aria-label="Download">
                    <Download size={18} />
                  </a>
                </div>
              ))}
            </div>
          ) : null}

          {tab === "links" && items.length ? (
            <div className="list-pad">
              {items.map((item, index) => {
                let host = item.url;
                try {
                  host = new URL(item.url).hostname;
                } catch {
                  /* keep raw */
                }
                return (
                  <div key={`${item.message_id}-${index}`} className="row link-row">
                    <span className="doc__icon"><Link2 size={20} /></span>
                    <button type="button" className="row__body all-media__open" onClick={() => goTo(item)}>
                      <span className="row__title">{host}</span>
                      <span className="row__subtitle">{item.url} · {chatName(item.room_id)}</span>
                    </button>
                    <a className="icon-btn" href={item.url} target="_blank" rel="noopener noreferrer" aria-label="Open link">
                      <ExternalLink size={16} />
                    </a>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>

    </div>,
    document.body,
  );
}
