import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Eye, MoreVertical, Pause, Play, Send, Trash2, Volume2, VolumeX, X } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { statusApi } from "../../api/endpoints";
import { loadStatus, openChatWith, sendText } from "../../store/actions";
import { dispatch, getState, useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { detailTime, listTime } from "../../utils/format";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { Avatar, IconButton, MenuButton, Spinner } from "../common/ui";
import { confirmAction } from "../common/dialogs";

const IMAGE_MS = 6000;
const STATUS_REACTIONS = ["😍", "😂", "😮", "😢", "🙏", "👍"];

/** Mark a status seen locally so the ring/dot update immediately. */
function markSeenLocally(statusId) {
  const state = getState();
  const feed = state.statusFeed.map((group) => {
    let changed = false;
    const statuses = group.statuses.map((status) => {
      if (status.id !== statusId || status.is_viewed) return status;
      changed = true;
      return { ...status, is_viewed: true };
    });
    return changed ? { ...group, statuses, unseen_count: statuses.filter((s) => !s.is_viewed).length } : group;
  });
  dispatch({ type: "status/set", feed, mine: state.myStatuses });
}

/** "Viewed by" sheet shown inside the viewer (the status stays paused while it's open). */
function ViewersSheet({ statusId, count, onClose }) {
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [result, setResult] = useState({ key: "", rows: null });
  const key = `${statusId}:${count}`;
  useEffect(() => {
    let cancelled = false;
    statusApi
      .viewers(statusId)
      .then((rows) => !cancelled && setResult({ key, rows: Array.isArray(rows) ? rows : rows?.results || [] }))
      .catch((error) => {
        if (cancelled) return;
        toast.error(errorMessage(error));
        setResult({ key, rows: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [statusId, key]);
  const rows = result.rows;
  return (
    <div className="status-sheet" role="dialog" aria-label="Viewed by" onPointerDown={(event) => event.stopPropagation()}>
      <header className="status-sheet__head">
        <strong>Viewed by {rows ? rows.length : count ?? ""}</strong>
        <IconButton icon={X} label="Close viewers" onClick={onClose} />
      </header>
      <div className="status-sheet__list">
        {!rows ? <div className="list-loading"><Spinner /></div> : null}
        {rows && !rows.length ? <p className="status-sheet__empty">No views yet</p> : null}
        {rows?.map((row) => (
          <div key={row.id} className="row row--static">
            <Avatar src={row.viewer?.profile?.profile_picture} name={displayUserName(row.viewer, contactMap)} size={40} />
            <span className="row__body">
              <span className="row__title">{displayUserName(row.viewer, contactMap)}</span>
              <span className="row__subtitle">{detailTime(row.viewed_at)}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Full-screen status viewer with progress bars, auto-advance, pause on hold,
 * reactions/replies for others' statuses and viewers/delete for your own.
 */
export default function StatusViewer({ groups, startGroup = 0, startStatusId, onClose }) {
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [groupIndex, setGroupIndex] = useState(startGroup);
  const group = groups[groupIndex];
  const firstUnseen = Math.max(0, group?.statuses.findIndex((status) => !status.is_viewed));
  const requested = startStatusId ? group?.statuses.findIndex((status) => Number(status.id) === Number(startStatusId)) : -1;
  const [index, setIndex] = useState(requested >= 0 ? requested : firstUnseen);
  const [progress, setProgress] = useState(0);
  const [paused, setPaused] = useState(false);
  const [muted, setMuted] = useState(false);
  const [reply, setReply] = useState("");
  const [viewers, setViewers] = useState(null);
  const videoRef = useRef(null);
  const status = group?.statuses[index];
  const isMine = Number(group?.user?.id) === Number(me.id);
  const liveViews = useStore((state) => (isMine && status ? state.myStatuses.find((item) => item.id === status.id)?.views_count : undefined));
  const viewsCount = liveViews ?? status?.views_count ?? 0;
  const owner = group?.user;
  const ownerName = isMine ? "My status" : displayUserName(owner, contactMap);

  const next = useCallback(() => {
    setProgress(0);
    if (index < group.statuses.length - 1) setIndex(index + 1);
    else if (groupIndex < groups.length - 1) {
      const nextGroup = groups[groupIndex + 1];
      setGroupIndex(groupIndex + 1);
      setIndex(Math.max(0, nextGroup.statuses.findIndex((s) => !s.is_viewed)));
    } else onClose();
  }, [index, group, groupIndex, groups, onClose]);

  const previous = useCallback(() => {
    setProgress(0);
    if (index > 0) setIndex(index - 1);
    else if (groupIndex > 0) {
      setGroupIndex(groupIndex - 1);
      setIndex(0);
    }
  }, [index, groupIndex]);

  // Record the view (server) and update the ring locally.
  useEffect(() => {
    if (!status || isMine || status.is_viewed) return;
    markSeenLocally(status.id);
    statusApi.view(status.id).catch(() => {});
  }, [status, isMine]);

  // Timer for images/text; videos advance on "ended".
  useEffect(() => {
    if (!status || paused || status.status_type === "VIDEO") return undefined;
    const started = Date.now() - progress * IMAGE_MS;
    const timer = window.setInterval(() => {
      const value = (Date.now() - started) / IMAGE_MS;
      if (value >= 1) {
        window.clearInterval(timer);
        next();
      } else setProgress(value);
    }, 50);
    return () => window.clearInterval(timer);
    // progress is read once when (re)starting
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, paused, next]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (paused) video.pause();
    else video.play().catch(() => {});
  }, [paused, status]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.target.tagName === "INPUT") return;
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") next();
      if (event.key === "ArrowLeft") previous();
      if (event.key === " ") setPaused((value) => !value);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [next, previous, onClose]);

  if (!group || !status) return null;

  async function react(emoji) {
    try {
      await statusApi.react(status.id, emoji);
      toast.success(`Reacted ${emoji}`);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  async function sendReply(event) {
    event.preventDefault();
    const value = reply.trim();
    if (!value) return;
    setReply("");
    try {
      const roomId = await openChatWith(owner);
      const summary = status.status_type === "TEXT" ? status.content : status.status_type === "VIDEO" ? "Video status" : "Photo status";
      await sendText(roomId, `↩︎ Status: “${String(summary || "").slice(0, 60)}”\n${value}`);
      toast.success("Reply sent");
      setPaused(false);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  function remove() {
    setPaused(true);
    confirmAction({
      title: "Delete this status update?",
      message: "It will be deleted for everyone who received it.",
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        try {
          await statusApi.remove(status.id);
          await loadStatus();
          toast("Status deleted");
          onClose();
        } catch (error) {
          toast.error(errorMessage(error));
        }
      },
    });
  }

  const media = mediaUrl(status.media);

  return createPortal(
    <div className="status-viewer" role="dialog" aria-label={`${ownerName} status`}>
      <div className="status-viewer__frame">
        <div className="status-viewer__bars">
          {group.statuses.map((item, itemIndex) => (
            <span key={item.id}>
              <span style={{ width: `${itemIndex < index ? 100 : itemIndex === index ? progress * 100 : 0}%` }} />
            </span>
          ))}
        </div>
        <header className="status-viewer__top">
          <Avatar src={owner?.profile?.profile_picture} name={ownerName} size={40} />
          <div className="status-viewer__who">
            <strong>{ownerName}</strong>
            <span>{listTime(status.created_at)}</span>
          </div>
          <IconButton icon={paused ? Play : Pause} label={paused ? "Play" : "Pause"} onClick={() => setPaused((value) => !value)} />
          {status.status_type === "VIDEO" ? <IconButton icon={muted ? VolumeX : Volume2} label={muted ? "Unmute" : "Mute"} onClick={() => setMuted((value) => !value)} /> : null}
          {isMine ? (
            <span onClickCapture={() => setPaused(true)}>
              <MenuButton
                icon={MoreVertical}
                label="Status options"
                items={[
                  { label: `Viewed by ${viewsCount}`, icon: Eye, onClick: () => setViewers(status.id) },
                  { label: "Delete", icon: Trash2, danger: true, onClick: remove },
                ]}
              />
            </span>
          ) : null}
          <IconButton icon={X} label="Close" onClick={onClose} />
        </header>

        <div
          className="status-viewer__content"
          style={status.status_type === "TEXT" ? { background: status.background_color, color: status.text_color } : undefined}
          onPointerDown={() => setPaused(true)}
          onPointerUp={() => setPaused(false)}
          onPointerLeave={() => setPaused(false)}
        >
          {status.status_type === "TEXT" ? <p className="status-viewer__text">{status.content}</p> : null}
          {status.status_type === "IMAGE" ? <img src={media} alt="Status" /> : null}
          {status.status_type === "VIDEO" ? (
            <video
              ref={videoRef}
              src={media}
              autoPlay
              playsInline
              muted={muted}
              onTimeUpdate={(event) => event.currentTarget.duration && setProgress(event.currentTarget.currentTime / event.currentTarget.duration)}
              onEnded={next}
            />
          ) : null}
          {status.status_type !== "TEXT" && status.content ? <p className="status-viewer__caption">{status.content}</p> : null}
        </div>

        <button type="button" className="status-viewer__nav status-viewer__nav--prev" onClick={previous} aria-label="Previous status" disabled={index === 0 && groupIndex === 0}>
          <ChevronLeft size={28} />
        </button>
        <button type="button" className="status-viewer__nav status-viewer__nav--next" onClick={next} aria-label="Next status">
          <ChevronRight size={28} />
        </button>

        {viewers ? <ViewersSheet statusId={viewers} count={viewsCount} onClose={() => { setViewers(null); setPaused(false); }} /> : null}

        <footer className="status-viewer__bottom" hidden={Boolean(viewers)}>
          {isMine ? (
            <button type="button" className="status-viewer__views" onClick={() => { setPaused(true); setViewers(status.id); }}>
              <Eye size={18} /> {viewsCount} view{viewsCount === 1 ? "" : "s"}
            </button>
          ) : (
            <>
              <div className="status-viewer__reactions">
                {STATUS_REACTIONS.map((emoji) => (
                  <button key={emoji} type="button" className="emoji" onClick={() => react(emoji)} aria-label={`React ${emoji}`}>
                    {emoji}
                  </button>
                ))}
              </div>
              <form className="status-viewer__reply" onSubmit={sendReply}>
                <input value={reply} onChange={(event) => setReply(event.target.value)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)} placeholder="Reply…" maxLength={1000} />
                <button type="submit" className="send-btn" aria-label="Send reply" disabled={!reply.trim()}>
                  <Send size={18} />
                </button>
              </form>
            </>
          )}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
