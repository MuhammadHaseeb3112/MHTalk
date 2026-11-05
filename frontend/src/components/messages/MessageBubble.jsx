import { memo, useRef, useState } from "react";
import {
  Ban,
  ChevronDown,
  Download,
  FileText,
  Forward,
  Image as ImageIcon,
  Phone,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  Pin,
  Play,
  RotateCw,
  Smile,
  Star,
  UserRound,
  Video,
  Video as VideoIcon,
} from "lucide-react";
import { mediaUrl } from "../../api/client";
import { emojiOnly } from "../../utils/emoji";
import { formatPhone } from "../../utils/phone";
import { clockTime, duration as formatDuration, fileSize } from "../../utils/format";
import { attachmentKind, callSummary, messageKind, parseSpecial, previewText, URL_PATTERN } from "../../utils/messages";
import { BubbleTail } from "../common/Icons";
import { Checkbox } from "../common/ui";
import { Ticks } from "../chat-list/ChatListItem";
import AudioPlayer from "./AudioPlayer";
import { LinkPreviewCard, LocationCard, PollCard, ViewOnceContent } from "./FeatureCards";

const EMOJI_ONLY = /^(?:\p{Extended_Pictographic}|\p{Emoji_Component}|‍|️|\s)+$/u;

function highlight(part, query, keyBase) {
  if (!query) return part;
  const needle = query.toLowerCase();
  const pieces = [];
  let rest = part;
  let cursor = rest.toLowerCase().indexOf(needle);
  let key = 0;
  while (cursor >= 0 && needle) {
    pieces.push(rest.slice(0, cursor));
    pieces.push(<mark key={`${keyBase}-${key++}`} className="search-hit">{rest.slice(cursor, cursor + needle.length)}</mark>);
    rest = rest.slice(cursor + needle.length);
    cursor = rest.toLowerCase().indexOf(needle);
  }
  pieces.push(rest);
  return pieces;
}

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Text with clickable links, search highlights and @mentions. ``mentions``
 * is ``[{ id, token: "@<phone>", label }]``: the stored token renders as a
 * highlighted, clickable "@Name".
 */
export function RichText({ text, query, mentions, onMention }) {
  const value = String(text ?? "");
  const parts = value.split(URL_PATTERN);
  const tokens = (mentions || []).filter((item) => item.token).sort((a, b) => b.token.length - a.token.length);
  const mentionRe = tokens.length ? new RegExp(`(${tokens.map((item) => escapeRegExp(item.token)).join("|")})`, "g") : null;
  return parts.map((part, index) => {
    if (index % 2 === 1) {
      return (
        <a key={index} href={part} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()}>
          {part}
        </a>
      );
    }
    if (!mentionRe) return <span key={index}>{highlight(part, query, index)}</span>;
    return (
      <span key={index}>
        {part.split(mentionRe).map((piece, pieceIndex) => {
          const mention = pieceIndex % 2 === 1 ? tokens.find((item) => item.token === piece) : null;
          if (!mention) return <span key={pieceIndex}>{highlight(piece, query, `${index}-${pieceIndex}`)}</span>;
          return (
            <button
              key={pieceIndex}
              type="button"
              className="mention"
              onClick={(event) => {
                event.stopPropagation();
                onMention?.(mention.id, event);
              }}
            >
              @{mention.label}
            </button>
          );
        })}
      </span>
    );
  });
}

/** Room the time/ticks need at the end of the last text line. */
function metaWidth(message, isOwn) {
  let width = 58; // time
  if (isOwn && !message.is_deleted) width += 20;
  if (message.is_edited && !message.is_deleted) width += 42;
  if (message.is_starred) width += 14;
  if (message.is_pinned) width += 14;
  return width;
}

function Meta({ message, isOwn, overlay }) {
  return (
    <span className={`bubble__meta ${overlay ? "bubble__meta--overlay" : ""}`}>
      {message.is_pinned ? <Pin size={11} /> : null}
      {message.is_starred ? <Star size={11} fill="currentColor" /> : null}
      {message.is_edited && !message.is_deleted ? <span className="bubble__edited">Edited</span> : null}
      <span>{clockTime(message.created_at)}</span>
      {isOwn && !message.is_deleted ? <Ticks message={message} size={16} /> : null}
    </span>
  );
}

function ReplyQuote({ reply, nameOf, colorOf, onJump, myId }) {
  if (!reply) return null;
  const attachment = reply.attachment;
  const kind = attachment ? attachmentKind(attachment) : null;
  const text = reply.is_deleted
    ? "This message was deleted"
    : reply.is_view_once || reply.message_type === "POLL" || reply.message_type === "LOCATION"
      ? previewText({ ...reply, attachments: attachment ? [attachment] : [] }, myId)
      : reply.content
      ? previewText({ ...reply, attachments: attachment ? [attachment] : [] }, myId)
      : kind === "image"
        ? "Photo"
        : kind === "video"
          ? "Video"
          : reply.message_type === "VOICE"
            ? "Voice message"
            : attachment?.file_name || "Message";
  return (
    <button
      type="button"
      className="quote"
      style={{ "--quote-color": colorOf(reply.sender_id) }}
      onClick={(event) => {
        event.stopPropagation();
        onJump(reply.id);
      }}
    >
      <span className="quote__body">
        <span className="quote__name">{nameOf(reply.sender_id)}</span>
        <span className="quote__text">{text}</span>
      </span>
      {kind === "image" && attachment.file && !reply.is_view_once ? <img className="quote__thumb" src={mediaUrl(attachment.file)} alt="" /> : null}
    </button>
  );
}

/**
 * WhatsApp-style media box: at most 330×330, never wider than the bubble,
 * very tall images are cropped to 3:4 and very wide ones to 2:1 (the full
 * picture opens in the viewer).
 */
function mediaBox(width, height) {
  const MAX = 330;
  if (!width || !height) return { width: MAX, height: 240 };
  const ratio = Math.min(2, Math.max(0.75, width / height));
  let w = MAX;
  let h = w / ratio;
  if (h > MAX) {
    h = MAX;
    w = h * ratio;
  }
  // Small images are shown at natural size (but not tiny).
  const scale = Math.min(1, Math.max(width / w, 150 / w));
  return { width: Math.round(w * scale), height: Math.round(h * scale) };
}

function ImageContent({ attachment, onOpen, progress, pending }) {
  const [size, setSize] = useState(null);
  const [failed, setFailed] = useState(false);
  const style = mediaBox(size?.w, size?.h);
  return (
    <button type="button" className="media media--image" style={style} onClick={(event) => { event.stopPropagation(); onOpen(); }} aria-label="Open photo">
      {failed ? (
        <span className="media__error">Image unavailable</span>
      ) : (
        <img
          src={mediaUrl(attachment.file)}
          alt={attachment.file_name || "Photo"}
          loading="lazy"
          onLoad={(event) => setSize({ w: event.currentTarget.naturalWidth, h: event.currentTarget.naturalHeight })}
          onError={() => setFailed(true)}
        />
      )}
      {pending ? <UploadOverlay progress={progress} /> : null}
    </button>
  );
}

/** GIF (from GIPHY): plays on its own, muted and looping, like WhatsApp. */
function GifContent({ payload }) {
  const style = mediaBox(payload.width, payload.height);
  return (
    <span className="media media--gif" style={style}>
      <video src={payload.mp4} poster={payload.still || undefined} autoPlay loop muted playsInline aria-label={payload.title || "GIF"} />
      <span className="media__gif-badge">GIF</span>
    </span>
  );
}

/** Sticker: transparent image, no bubble. */
function StickerContent({ attachment, pending }) {
  return (
    <span className="sticker-msg">
      <img src={mediaUrl(attachment.file)} alt="Sticker" loading="lazy" draggable={false} />
      {pending ? <span className="sticker-msg__pending" /> : null}
    </span>
  );
}

function VideoContent({ attachment, onOpen, progress, pending }) {
  const [meta, setMeta] = useState(null);
  const [failed, setFailed] = useState(false);
  const style = mediaBox(meta?.w, meta?.h);
  return (
    <button type="button" className="media media--video" style={style} onClick={(event) => { event.stopPropagation(); onOpen(); }} aria-label="Play video">
      {failed ? (
        <span className="media__error">Video preview unavailable</span>
      ) : (
        <video
          src={`${mediaUrl(attachment.file)}#t=0.1`}
          preload="metadata"
          muted
          playsInline
          onLoadedMetadata={(event) => {
            const video = event.currentTarget;
            setMeta({ w: video.videoWidth, h: video.videoHeight, duration: Number.isFinite(video.duration) ? video.duration : null });
          }}
          onError={() => setFailed(true)}
        />
      )}
      {pending ? (
        <UploadOverlay progress={progress} />
      ) : (
        <span className="media__play"><Play size={28} fill="currentColor" /></span>
      )}
      <span className="media__badge">
        <Video size={14} fill="currentColor" /> {meta?.duration ? formatDuration(meta.duration) : ""}
      </span>
    </button>
  );
}

function UploadOverlay({ progress }) {
  const value = Math.max(2, Number(progress) || 0);
  return (
    <span className="upload-overlay" aria-label={`Uploading ${value}%`}>
      <svg viewBox="0 0 36 36" width="46" height="46">
        <circle cx="18" cy="18" r="15" fill="rgba(0,0,0,.45)" stroke="rgba(255,255,255,.25)" strokeWidth="3" />
        <circle cx="18" cy="18" r="15" fill="none" stroke="#fff" strokeWidth="3" strokeDasharray={`${(value / 100) * 94} 94`} transform="rotate(-90 18 18)" strokeLinecap="round" />
      </svg>
    </span>
  );
}

function DocumentContent({ attachment, pending, progress }) {
  const name = attachment.file_name || "Document";
  const ext = (name.split(".").pop() || "file").slice(0, 4).toUpperCase();
  return (
    <a
      className="doc"
      href={pending ? undefined : mediaUrl(attachment.file)}
      target="_blank"
      rel="noopener noreferrer"
      download={name}
      onClick={(event) => event.stopPropagation()}
    >
      <span className={`doc__icon doc__icon--${ext.toLowerCase()}`}>{ext === "PDF" ? "PDF" : <FileText size={22} />}</span>
      <span className="doc__body">
        <span className="doc__name">{name}</span>
        <span className="doc__meta">
          {ext} · {fileSize(attachment.file_size)}
          {pending ? ` · ${progress || 0}%` : ""}
        </span>
      </span>
      {!pending ? <Download size={20} className="doc__dl" /> : null}
    </a>
  );
}

function CallCard({ event, myId, onCall }) {
  const summary = callSummary(event, myId);
  const Icon = summary.missed ? PhoneMissed : summary.outgoing ? PhoneOutgoing : PhoneIncoming;
  return (
    <button type="button" className={`call-card ${summary.missed ? "is-missed" : ""}`} onClick={(e) => { e.stopPropagation(); onCall(summary.video ? "video" : "audio"); }}>
      <span className="call-card__icon">{summary.video ? <Video size={20} /> : <Icon size={20} />}</span>
      <span className="call-card__body">
        <span className="call-card__title">{summary.label}</span>
        <span className="call-card__sub">
          {summary.answered ? formatDuration(event.duration) : summary.missed ? (summary.group ? "Tap to call the group" : "Tap to call back") : "Tap to call again"}
        </span>
      </span>
      <Phone size={16} className="call-card__again" />
    </button>
  );
}

/** Reaction or reply to a status: WhatsApp's "Name · Status" card + the reply. */
function StatusReactionCard({ payload, onOpen, ownerName }) {
  const media = payload.status_media ? mediaUrl(payload.status_media) : "";
  const type = payload.status_type;
  const emojiReply = payload.emoji || (payload.text && emojiOnly(payload.text)) || "";
  let thumb;
  if (media && type === "IMAGE") thumb = <img src={media} alt="" />;
  else if (media && type === "VIDEO") thumb = <video src={`${media}#t=0.5`} preload="metadata" muted playsInline />;
  else
    thumb = (
      <span className="status-reaction__text-thumb" style={{ background: payload.status_bg || "var(--accent)", color: payload.status_fg || "#fff" }}>
        {(payload.status_text || "").slice(0, 40)}
      </span>
    );
  return (
    <div className="status-reaction is-clickable">
      <div
        className="status-reaction__preview"
        role="button"
        tabIndex={0}
        title="View status"
        onClick={(event) => {
          event.stopPropagation();
          onOpen();
        }}
        onKeyDown={(event) => event.key === "Enter" && onOpen()}
      >
        <span className="status-reaction__who">
          <strong>{ownerName} · Status</strong>
          <span className="status-reaction__type">
            {type === "VIDEO" ? <><VideoIcon size={14} /> Video</> : type === "IMAGE" ? <><ImageIcon size={14} /> Photo</> : payload.status_text || "Status"}
          </span>
        </span>
        <span className="status-reaction__thumb">{thumb}</span>
      </div>
      {emojiReply ? <span className="status-reaction__emoji">{emojiReply}</span> : <span className="status-reaction__reply">{payload.text}</span>}
    </div>
  );
}

function Reactions({ reactions, myId, onClick }) {
  if (!reactions?.length) return null;
  const counts = new Map();
  reactions.forEach((reaction) => counts.set(reaction.emoji, (counts.get(reaction.emoji) || 0) + 1));
  const mine = reactions.some((reaction) => Number(reaction.user_id) === Number(myId));
  return (
    <button type="button" className={`reactions ${mine ? "is-mine" : ""}`} onClick={(event) => { event.stopPropagation(); onClick(event); }}>
      {[...counts.keys()].slice(0, 3).map((emoji) => (
        <span key={emoji} className="emoji">{emoji}</span>
      ))}
      {reactions.length > 1 ? <span className="reactions__count">{reactions.length}</span> : null}
    </button>
  );
}

/**
 * One message row. All interactions are reported through `onAction(type,
 * message, event)` so the component stays memoised during scrolling.
 */
function MessageBubble({
  message,
  myId,
  isOwn,
  showTail,
  senderName,
  senderColor,
  senderAvatar,
  nameOf,
  colorOf,
  userOf,
  mentionOf,
  selectMode,
  selected,
  highlighted,
  searchQuery,
  onAction,
}) {
  // Touch screens: press and hold a bubble to open its menu.
  const pressRef = useRef(null);
  const cancelPress = () => {
    if (pressRef.current) window.clearTimeout(pressRef.current.timer);
    pressRef.current = null;
  };
  const startPress = (event) => {
    if (selectMode || pending || event.touches.length !== 1) return;
    const touch = event.touches[0];
    const point = { clientX: touch.clientX, clientY: touch.clientY, type: "longpress" };
    cancelPress();
    pressRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      timer: window.setTimeout(() => {
        pressRef.current = null;
        navigator.vibrate?.(15);
        onAction("menu", message, point);
      }, 450),
    };
  };
  const movePress = (event) => {
    const touch = event.touches[0];
    if (pressRef.current && touch && Math.hypot(touch.clientX - pressRef.current.x, touch.clientY - pressRef.current.y) > 10) cancelPress();
  };

  const kind = messageKind(message);
  const attachments = message.attachments || [];
  const first = attachments[0];
  const special = kind === "call" || kind === "status_reaction" || kind === "gif" ? parseSpecial(message.content) : null;
  const caption = kind === "image" || kind === "video" ? message.content : "";
  const emojiOnly = (kind === "text" && message.content && message.content.length <= 24 && EMOJI_ONLY.test(message.content)) || kind === "sticker";
  const isMedia = ((kind === "image" || kind === "video") && !caption) || kind === "gif";
  const pending = Boolean(message._pending);

  const act = (type) => (event) => onAction(type, message, event);
  const mentions = message.mentions?.length && mentionOf ? message.mentions.map((id) => mentionOf(id)).filter(Boolean) : null;
  const onMention = (userId, event) => onAction("mention", message, { userId, event });

  let body;
  switch (kind) {
    case "deleted":
      body = (
        <span className="bubble__deleted">
          <Ban size={15} /> {isOwn ? "You deleted this message" : "This message was deleted"}
        </span>
      );
      break;
    case "image":
      body = <ImageContent attachment={first} onOpen={() => onAction("openMedia", message)} progress={message._progress} pending={pending} />;
      break;
    case "gif":
      body = <GifContent payload={special} />;
      break;
    case "sticker":
      body = <StickerContent attachment={first} pending={pending} />;
      break;
    case "video":
      body = <VideoContent attachment={first} onOpen={() => onAction("openMedia", message)} progress={message._progress} pending={pending} />;
      break;
    case "voice":
      body = (
        <AudioPlayer
          src={message.voice_note.audio}
          seconds={message.voice_note.duration}
          waveform={message.voice_note.waveform}
          isVoice
          avatarSrc={senderAvatar}
          avatarName={senderName}
          seed={message.id}
          outgoing={isOwn}
          played={isOwn ? message.is_read : true}
        />
      );
      break;
    case "audio":
      body = <AudioPlayer src={first.file} fileName={first.file_name} seed={message.id} outgoing={isOwn} />;
      break;
    case "document":
      body = <DocumentContent attachment={first} pending={pending} progress={message._progress} />;
      break;
    case "call":
      body = <CallCard event={special} myId={myId} onCall={(type) => onAction("call", message, { type })} />;
      break;
    case "status_reaction":
      body = (
        <StatusReactionCard
          payload={special}
          ownerName={Number(special?.owner_id) === Number(myId) ? "You" : nameOf(special?.owner_id)}
          onOpen={() => onAction("openStatus", message, special)}
        />
      );
      break;
    case "poll":
      body = <PollCard message={message} myId={myId} userOf={userOf} nameOf={nameOf} onAction={onAction} />;
      break;
    case "view_once":
      body = <ViewOnceContent message={message} myId={myId} pending={pending} progress={message._progress} onAction={onAction} />;
      break;
    case "location":
      body = <LocationCard content={message.content} />;
      break;
    case "contact": {
      const card = typeof message.content === "object" && message.content ? message.content : {};
      body = (
        <div className="contact-card">
          <button
            type="button"
            className="contact-card__main"
            onClick={(event) => {
              event.stopPropagation();
              onAction("contact", message, { event, action: "menu" });
            }}
            aria-label={`Contact ${card.name || card.phone || ""} options`}
          >
            <span className="contact-card__avatar"><UserRound size={22} /></span>
            <span className="contact-card__text">
              <span className="contact-card__name">{card.name || formatPhone(card.phone)}</span>
              {card.name && card.phone ? <span className="contact-card__phone">{formatPhone(card.phone)}</span> : null}
            </span>
          </button>
          <div className="contact-card__actions">
            <button type="button" onClick={(event) => { event.stopPropagation(); onAction("contact", message, { event, action: "message" }); }}>
              Message
            </button>
            <button type="button" onClick={(event) => { event.stopPropagation(); onAction("contact", message, { event, action: "menu" }); }}>
              More
            </button>
          </div>
        </div>
      );
      break;
    }
    default:
      body = (
        <>
          {message.link_preview ? <LinkPreviewCard preview={message.link_preview} /> : null}
          <span className={`bubble__text ${emojiOnly ? "bubble__text--emoji" : ""}`}>
            <RichText text={message.content} query={searchQuery} mentions={mentions} onMention={onMention} />
          </span>
        </>
      );
  }

  const forwarded = message.forwarded_from && !message.is_deleted;

  return (
    <div
      className={`msg-row ${isOwn ? "msg-row--out" : "msg-row--in"} ${showTail ? "has-tail" : ""} ${selectMode ? "is-selecting" : ""} ${selected ? "is-selected" : ""} ${highlighted ? "is-highlighted" : ""}`}
      data-message-id={message.id || message.client_message_id}
      onClick={selectMode && !message.is_deleted ? act("toggleSelect") : undefined}
      onDoubleClick={!selectMode && !message.is_deleted && !pending ? act("reply") : undefined}
    >
      {selectMode ? (
        <span className="msg-row__check">
          <Checkbox checked={selected} onChange={() => onAction("toggleSelect", message)} label="Select message" />
        </span>
      ) : null}
      <div className="msg-row__inner">
        <div
          className={`bubble bubble--${isOwn ? "out" : "in"} ${isMedia ? "bubble--media" : ""} ${emojiOnly ? "bubble--emoji" : ""} bubble--${kind}`}
          style={{ "--meta-w": `${metaWidth(message, isOwn)}px` }}
          onContextMenu={!selectMode && !pending ? (event) => { event.preventDefault(); onAction("menu", message, event); } : undefined}
          onTouchStart={startPress}
          onTouchMove={movePress}
          onTouchEnd={cancelPress}
          onTouchCancel={cancelPress}
        >
          {showTail && !emojiOnly ? <BubbleTail side={isOwn ? "out" : "in"} /> : null}
          {senderName && !isOwn ? (
            <span className="bubble__sender" style={{ color: senderColor }}>
              {senderName}
            </span>
          ) : null}
          {forwarded ? (
            <span className="bubble__forwarded">
              <Forward size={14} /> Forwarded
            </span>
          ) : null}
          {message.reply_to ? <ReplyQuote reply={message.reply_to} nameOf={nameOf} colorOf={colorOf} onJump={(id) => onAction("jump", message, { id })} myId={myId} /> : null}
          {body}
          {caption ? (
            <span className="bubble__text bubble__caption">
              <RichText text={caption} query={searchQuery} mentions={mentions} onMention={onMention} />
            </span>
          ) : null}
          {kind !== "call" ? <Meta message={message} isOwn={isOwn} overlay={isMedia} /> : <Meta message={message} isOwn={false} />}
          {!selectMode && !pending && !message.is_deleted ? (
            <button type="button" className="bubble__chevron" aria-label="Message options" onClick={(event) => { event.stopPropagation(); onAction("menu", message, event); }}>
              <ChevronDown size={18} />
            </button>
          ) : null}
        </div>
        {!selectMode && !pending && !message.is_deleted ? (
          <div className="msg-row__side">
            <button type="button" className="side-btn" aria-label="React" onClick={(event) => { event.stopPropagation(); onAction("react", message, event); }}>
              <Smile size={18} />
            </button>
            {kind !== "text" && kind !== "call" && kind !== "view_once" ? (
              <button type="button" className="side-btn" aria-label="Forward" onClick={(event) => { event.stopPropagation(); onAction("forward", message, event); }}>
                <Forward size={18} />
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      {message._failed ? (
        <button type="button" className="msg-row__failed" onClick={(event) => { event.stopPropagation(); onAction("retry", message); }}>
          <RotateCw size={13} /> Not sent. Tap to retry
        </button>
      ) : null}
      <Reactions reactions={message.reactions} myId={myId} onClick={(event) => onAction("reactions", message, event)} />
    </div>
  );
}

export default memo(MessageBubble);
