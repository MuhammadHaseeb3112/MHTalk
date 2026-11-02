import { useEffect, useState } from "react";
import { ChevronRight, FileText, Play } from "lucide-react";
import { mediaUrl } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { useStore } from "../../store/store";

/** "Media, links and docs" summary row with the latest thumbnails. */
export function MediaSummary({ roomId, onOpen }) {
  const [state, setState] = useState({ media: [], counts: null });
  const version = useStore((s) => s.rooms[roomId]?.lastMessage?.id);

  useEffect(() => {
    let cancelled = false;
    Promise.all([chatApi.sharedMedia(roomId, "media"), chatApi.sharedMedia(roomId, "docs"), chatApi.sharedMedia(roomId, "links"), chatApi.sharedMedia(roomId, "audio")])
      .then(([media, docs, links, audio]) => {
        if (cancelled) return;
        setState({ media: media.results.slice(0, 4), counts: media.count + docs.count + links.count + audio.count });
      })
      .catch(() => !cancelled && setState({ media: [], counts: 0 }));
    return () => {
      cancelled = true;
    };
  }, [roomId, version]);

  return (
    <div className="info-section">
      <button type="button" className="info-row info-row--link" onClick={onOpen}>
        <span>Media, links and docs</span>
        <span className="info-row__count">
          {state.counts ?? ""} <ChevronRight size={18} />
        </span>
      </button>
      {state.media.length ? (
        <div className="media-thumbs">
          {state.media.map((item) => (
            <button key={item.id} type="button" className="media-thumb" onClick={onOpen}>
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
      ) : state.counts === 0 ? (
        <p className="info-muted">No media, links or docs yet</p>
      ) : null}
    </div>
  );
}

export function InfoRow({ icon: Icon, title, subtitle, onClick, danger, trailing }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} className={`info-action ${danger ? "is-danger" : ""}`} onClick={onClick}>
      {Icon ? <Icon size={20} /> : null}
      <span className="info-action__body">
        <span className="info-action__title">{title}</span>
        {subtitle ? <span className="info-action__subtitle">{subtitle}</span> : null}
      </span>
      {trailing}
    </Tag>
  );
}

export function DocIcon() {
  return <FileText size={22} />;
}
