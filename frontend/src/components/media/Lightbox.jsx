import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Download, Forward, Maximize2, MessageSquareReply, X } from "lucide-react";
import { mediaUrl } from "../../api/client";
import { detailTime } from "../../utils/format";
import { attachmentKind } from "../../utils/messages";
import { Avatar, IconButton } from "../common/ui";

/**
 * Full-screen media viewer for a conversation's photos and videos with
 * previous/next navigation (arrows, keyboard, thumbnails), download,
 * forward and "go to message".
 */
export default function Lightbox({ items, startIndex = 0, nameOf, onClose, onForward, onGoTo }) {
  const [index, setIndex] = useState(startIndex);
  const videoRef = useRef(null);
  const stripRef = useRef(null);
  const current = items[index];
  // Swipe left / right to see the next or previous photo (phones and touchpads).
  const swipe = useRef(null);
  const [dragX, setDragX] = useState(0);

  const go = useCallback((step) => setIndex((value) => Math.min(items.length - 1, Math.max(0, value + step))), [items.length]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") go(1);
      if (event.key === "ArrowLeft") go(-1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  useEffect(() => {
    stripRef.current?.querySelector(".is-active")?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [index]);

  if (!current) return null;
  const kind = attachmentKind(current.attachment);
  const url = mediaUrl(current.attachment.file);
  const sender = current.message.sender;

  return createPortal(
    <div className="lightbox" role="dialog" aria-label="Media viewer">
      <header className="lightbox__top">
        <Avatar src={sender?.profile?.profile_picture} name={nameOf(sender?.id)} size={40} />
        <div className="lightbox__who">
          <strong>{nameOf(sender?.id)}</strong>
          <span>{detailTime(current.message.created_at)}</span>
        </div>
        <div className="lightbox__actions">
          {onGoTo ? <IconButton icon={MessageSquareReply} label="Go to message" onClick={() => { onGoTo(current.message); onClose(); }} /> : null}
          {onForward ? <IconButton icon={Forward} label="Forward" onClick={() => onForward(current.message)} /> : null}
          <a className="icon-btn" href={url} download={current.attachment.file_name || true} target="_blank" rel="noopener noreferrer" aria-label="Download" data-tooltip="Download">
            <Download size={20} />
          </a>
          {kind === "video" ? <IconButton icon={Maximize2} label="Full screen" onClick={() => videoRef.current?.requestFullscreen?.()} /> : null}
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
      </header>

      <div
        className="lightbox__stage"
        onClick={(event) => event.target === event.currentTarget && !swipe.current?.moved && onClose()}
        onPointerDown={(event) => {
          if (event.pointerType === "mouse" || event.target.closest("button, video")) return;
          swipe.current = { x: event.clientX, y: event.clientY, moved: false };
        }}
        onPointerMove={(event) => {
          const start = swipe.current;
          if (!start) return;
          const dx = event.clientX - start.x;
          if (!start.moved && (Math.abs(dx) < 8 || Math.abs(dx) < Math.abs(event.clientY - start.y))) return;
          start.moved = true;
          const atEdge = (dx > 0 && index === 0) || (dx < 0 && index === items.length - 1);
          setDragX(atEdge ? dx / 4 : dx);
        }}
        onPointerUp={(event) => {
          const start = swipe.current;
          swipe.current = start?.moved ? { moved: true } : null;
          window.setTimeout(() => { swipe.current = null; }, 0);
          if (!start?.moved) return;
          const dx = event.clientX - start.x;
          setDragX(0);
          if (dx < -60) go(1);
          else if (dx > 60) go(-1);
        }}
        onPointerCancel={() => {
          swipe.current = null;
          setDragX(0);
        }}
      >
        {index > 0 ? (
          <button type="button" className="lightbox__nav lightbox__nav--prev" onClick={() => go(-1)} aria-label="Previous">
            <ChevronLeft size={30} />
          </button>
        ) : null}
        {kind === "video" ? (
          <video key={url} ref={videoRef} src={url} controls autoPlay playsInline />
        ) : (
          <img
            key={url}
            src={url}
            alt={current.attachment.file_name || "Photo"}
            draggable={false}
            className={dragX ? "is-dragging" : ""}
            style={dragX ? { transform: `translateX(${dragX}px)`, opacity: Math.max(0.4, 1 - Math.abs(dragX) / 600) } : undefined}
          />
        )}
        {index < items.length - 1 ? (
          <button type="button" className="lightbox__nav lightbox__nav--next" onClick={() => go(1)} aria-label="Next">
            <ChevronRight size={30} />
          </button>
        ) : null}
      </div>
      {current.message.content ? <p className="lightbox__caption">{current.message.content}</p> : null}
      {items.length > 1 ? <p className="lightbox__count">{index + 1} of {items.length}</p> : null}

      {items.length > 1 ? (
        <div className="lightbox__strip" ref={stripRef}>
          {items.map((item, itemIndex) => {
            const itemKind = attachmentKind(item.attachment);
            return (
              <button key={`${item.message.id}-${item.attachment.id}`} type="button" className={itemIndex === index ? "is-active" : ""} onClick={() => setIndex(itemIndex)} aria-label={`Show item ${itemIndex + 1}`}>
                {itemKind === "video" ? <video src={`${mediaUrl(item.attachment.file)}#t=0.1`} muted preload="metadata" /> : <img src={mediaUrl(item.attachment.file)} alt="" loading="lazy" />}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>,
    document.body,
  );
}
