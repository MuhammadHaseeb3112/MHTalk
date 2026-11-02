import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, FileText, Headphones, Link2, Play } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { useStore } from "../../store/store";
import { fileSize, listTime } from "../../utils/format";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { EmptyState, PanelHeader, Spinner } from "../common/ui";
import { useApp } from "../layout/AppContext";
import Lightbox from "../media/Lightbox";

const TABS = [
  { id: "media", label: "Media" },
  { id: "docs", label: "Docs" },
  { id: "links", label: "Links" },
  { id: "audio", label: "Audio" },
];

/** Shared media / documents / links of this conversation only. */
export default function SharedMedia({ roomId, tab: initialTab = "media" }) {
  const app = useApp();
  const room = useStore((state) => state.rooms[roomId]);
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [tab, setTab] = useState(initialTab);
  const [data, setData] = useState({});
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState(null);

  useEffect(() => {
    if (data[tab]) return;
    chatApi
      .sharedMedia(roomId, tab)
      .then((result) => setData((current) => ({ ...current, [tab]: result.results })))
      .catch((err) => setError(errorMessage(err)));
  }, [roomId, tab, data]);

  const items = data[tab];
  const nameOf = (userId) => {
    const user = room?.participants.find((p) => Number(p.user?.id) === Number(userId))?.user;
    return user ? displayUserName(user, contactMap, { me }) : "Unknown";
  };

  return (
    <section className="panel info-panel">
      <PanelHeader title="Media, links and docs" onBack={() => app.openDrawer(room?.isGroup ? "group" : "contact", { roomId })} variant="sub" />
      <div className="tabs" role="tablist">
        {TABS.map((item) => (
          <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "is-active" : ""} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="panel__scroll">
        {!items && !error ? <div className="list-loading"><Spinner /></div> : null}
        {error ? <EmptyState text={error} /> : null}
        {items && !items.length ? <EmptyState text={`No ${TABS.find((t) => t.id === tab).label.toLowerCase()} shared in this chat`} /> : null}

        {tab === "media" && items?.length ? (
          <div className="media-grid">
            {items.map((item, index) => (
              <button key={item.id} type="button" className="media-thumb" onClick={() => setViewer(index)}>
                {item.mime_type?.startsWith("video/") ? (
                  <>
                    <video src={`${mediaUrl(item.file)}#t=0.1`} muted preload="metadata" />
                    <span className="media-thumb__play"><Play size={16} fill="currentColor" /></span>
                  </>
                ) : (
                  <img src={mediaUrl(item.file)} alt="" loading="lazy" />
                )}
              </button>
            ))}
          </div>
        ) : null}

        {(tab === "docs" || tab === "audio") && items?.length ? (
          <div className="list-pad">
            {items.map((item) => (
              <a key={item.id} className="row doc-row" href={mediaUrl(item.file)} target="_blank" rel="noopener noreferrer" download={item.file_name}>
                <span className="doc__icon">{tab === "audio" ? <Headphones size={20} /> : <FileText size={20} />}</span>
                <span className="row__body">
                  <span className="row__title">{item.file_name}</span>
                  <span className="row__subtitle">
                    {fileSize(item.file_size)} · {nameOf(item.sender_id)} · {listTime(item.created_at)}
                  </span>
                </span>
                <Download size={18} className="doc__dl" />
              </a>
            ))}
          </div>
        ) : null}

        {tab === "links" && items?.length ? (
          <div className="list-pad">
            {items.map((item, index) => {
              let host = item.url;
              try {
                host = new URL(item.url).hostname;
              } catch {
                /* keep raw */
              }
              return (
                <a key={`${item.message_id}-${index}`} className="row link-row" href={item.url} target="_blank" rel="noopener noreferrer">
                  <span className="doc__icon"><Link2 size={20} /></span>
                  <span className="row__body">
                    <span className="row__title">{host}</span>
                    <span className="row__subtitle">{item.url}</span>
                  </span>
                  <ExternalLink size={16} className="doc__dl" />
                </a>
              );
            })}
          </div>
        ) : null}
      </div>
      {viewer !== null && data.media ? (
        <Lightbox
          items={data.media.map((item) => ({
            message: { id: item.message_id, sender: room?.participants.find((p) => Number(p.user?.id) === Number(item.sender_id))?.user || { id: item.sender_id }, created_at: item.created_at, content: item.caption },
            attachment: item,
          }))}
          startIndex={viewer}
          nameOf={nameOf}
          onClose={() => setViewer(null)}
          onGoTo={(message) => window.dispatchEvent(new CustomEvent("mhtalk:jump-to", { detail: message.id }))}
        />
      ) : null}
    </section>
  );
}
