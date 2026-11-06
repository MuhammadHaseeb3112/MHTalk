import { useEffect, useState, useSyncExternalStore } from "react";
import { CheckCheck, ListChecks, MapPin, Radio } from "lucide-react";
import { isSharingLive, stopLiveLocation, subscribeLiveLocation } from "../../services/liveLocation";
import { clockTime } from "../../utils/format";
import { googleMapsUrl, myPollVotes, osmTilePoint, viewOnceState } from "../../utils/messages";
import { Avatar } from "../common/ui";

/**
 * Bubble bodies for polls, view once media, shared locations and link
 * previews (WhatsApp look). Interactions go through ``onAction`` like the
 * rest of MessageBubble.
 */

/* ---------------------------------------------------------------- Poll */

export function PollCard({ message, myId, userOf, nameOf, onAction }) {
  const poll = message.poll;
  if (!poll) return null;
  const mine = myPollVotes(poll, myId);
  const total = poll.total_voters || 0;
  const pending = !message.id;
  return (
    <div className="poll" role="group" aria-label={`Poll: ${poll.question}`}>
      <div className="poll__question">{poll.question}</div>
      <div className="poll__hint">
        {poll.allow_multiple ? <ListChecks size={14} /> : <CheckCheck size={14} />}
        {poll.allow_multiple ? "Select one or more" : "Select one"}
      </div>
      <div className="poll__options">
        {poll.options.map((option) => {
          const chosen = mine.includes(option.id);
          const share = total ? Math.round(((option.count || 0) / total) * 100) : 0;
          const voters = (option.voters || []).slice(-3).reverse();
          return (
            <button
              key={option.id}
              type="button"
              className={`poll__option ${chosen ? "is-chosen" : ""}`}
              disabled={pending}
              aria-pressed={chosen}
              aria-label={`${option.text}, ${option.count || 0} vote${option.count === 1 ? "" : "s"}`}
              onClick={(event) => {
                event.stopPropagation();
                onAction("vote", message, { optionId: option.id });
              }}
            >
              <span className={`poll__mark ${poll.allow_multiple ? "poll__mark--box" : ""}`} aria-hidden>
                {chosen ? <svg viewBox="0 0 16 16" width="12" height="12"><path d="M3.5 8.4 6.6 11.4 12.6 4.8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg> : null}
              </span>
              <span className="poll__body">
                <span className="poll__row">
                  <span className="poll__text">{option.text}</span>
                  <span className="poll__voters">
                    {voters.map((id) => {
                      const user = userOf(id);
                      return <Avatar key={id} src={user?.profile?.profile_picture} name={nameOf(id)} size={18} className="poll__avatar" />;
                    })}
                    <span className="poll__count">{option.count || 0}</span>
                  </span>
                </span>
                <span className="poll__bar"><span style={{ width: `${share}%` }} /></span>
              </span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="poll__view"
        disabled={!total || pending}
        onClick={(event) => {
          event.stopPropagation();
          onAction("pollVotes", message);
        }}
      >
        {total ? "View votes" : "No votes yet"}
      </button>
    </div>
  );
}

/* ---------------------------------------------------------------- View once */

export function ViewOnceIcon({ size = 20, opened }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={`view-once-icon ${opened ? "is-opened" : ""}`}>
      <circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray={opened ? "0" : "3.2 2.2"} />
      {opened ? null : <path d="M10.4 9.2 12.6 7.8V16.4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  );
}

export function ViewOnceContent({ message, myId, pending, progress, onAction }) {
  const { mine, video, voice, opened } = viewOnceState(message, myId);
  const label = voice ? "Voice message" : video ? "Video" : "Photo";
  const canOpen = !mine && !opened && !pending && message.id;
  const text = pending ? `${label} · ${progress || 0}%` : opened ? "Opened" : label;
  return (
    <button
      type="button"
      className={`view-once ${opened ? "is-opened" : ""} ${canOpen ? "is-openable" : ""}`}
      disabled={!canOpen}
      aria-label={canOpen ? `Open view once ${label.toLowerCase()}` : `View once ${label.toLowerCase()}${opened ? ", opened" : ""}`}
      onClick={(event) => {
        event.stopPropagation();
        if (canOpen) onAction("viewOnce", message);
      }}
    >
      <ViewOnceIcon size={22} opened={opened} />
      <span className="view-once__text">{text}</span>
    </button>
  );
}

/* ---------------------------------------------------------------- Location */

const TILE = 256;

/**
 * Static OpenStreetMap preview: the tiles around the point are positioned so
 * the shared location sits exactly under the centred pin.
 */
export function MapPreview({ latitude, longitude, width = 270, height = 150, zoom = 15 }) {
  const [failed, setFailed] = useState(false);
  const { x, y } = osmTilePoint(latitude, longitude, zoom);
  const left = x * TILE - width / 2;
  const top = y * TILE - height / 2;
  const tiles = [];
  const max = 2 ** zoom;
  for (let tx = Math.floor(left / TILE); tx <= Math.floor((left + width) / TILE); tx += 1) {
    for (let ty = Math.floor(top / TILE); ty <= Math.floor((top + height) / TILE); ty += 1) {
      if (ty < 0 || ty >= max) continue;
      const wrapped = ((tx % max) + max) % max;
      tiles.push({ key: `${tx}-${ty}`, src: `https://tile.openstreetmap.org/${zoom}/${wrapped}/${ty}.png`, left: tx * TILE - left, top: ty * TILE - top });
    }
  }
  return (
    <span className="map-preview" style={{ width, height }}>
      {failed ? <span className="map-preview__fallback"><MapPin size={28} /></span> : null}
      {tiles.map((tile) => (
        <img
          key={tile.key}
          src={tile.src}
          alt=""
          width={TILE}
          height={TILE}
          draggable={false}
          referrerPolicy="no-referrer-when-downgrade"
          style={{ left: tile.left, top: tile.top }}
          onError={() => setFailed(true)}
        />
      ))}
      <svg className="map-preview__pin" viewBox="0 0 24 34" width="26" height="36" aria-hidden>
        <path d="M12 1C6 1 1.5 5.5 1.5 11.3 1.5 19 12 33 12 33s10.5-14 10.5-21.7C22.5 5.5 18 1 12 1Z" fill="#f15c6d" stroke="#8c1d2b" strokeWidth="1" />
        <circle cx="12" cy="11.3" r="3.8" fill="#fff" />
      </svg>
      <span className="map-preview__credit">© OpenStreetMap</span>
    </span>
  );
}

/** Current time, refreshed every 30 s while ``active`` (for "Live until"). */
function useClock(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function LiveLocationFooter({ card, messageId, mine }) {
  const until = Date.parse(card.live_until || "");
  const now = useClock(!card.stopped);
  const sharingHere = useSyncExternalStore(subscribeLiveLocation, () => isSharingLive(messageId));
  const active = !card.stopped && Number.isFinite(until) && until > now;
  return (
    <span className="location-card__live">
      <span className={`location-card__live-icon ${active ? "is-active" : ""}`}><Radio size={16} /></span>
      <span className="location-card__live-text">
        <strong>{active ? "Live location" : "Live location ended"}</strong>
        <small>{active ? `Live until ${clockTime(card.live_until)}` : card.updated_at ? `Last updated ${clockTime(card.updated_at)}` : ""}</small>
      </span>
      {mine && active ? (
        <button
          type="button"
          className="location-card__stop"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            stopLiveLocation(messageId);
          }}
        >
          {sharingHere ? "Stop sharing" : "Stop"}
        </button>
      ) : null}
    </span>
  );
}

export function LocationCard({ content, messageId, mine = false }) {
  const card = content && typeof content === "object" ? content : {};
  const latitude = Number(card.latitude);
  const longitude = Number(card.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return <span className="bubble__text">📍 Location</span>;
  const url = googleMapsUrl(latitude, longitude);
  if (card.live) {
    return (
      <span className="location-card location-card--live">
        <a href={url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()} aria-label="Open live location in Google Maps">
          <MapPreview latitude={latitude} longitude={longitude} />
        </a>
        <LiveLocationFooter card={card} messageId={messageId} mine={mine} />
      </span>
    );
  }
  return (
    <a className="location-card" href={url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()} aria-label="Open location in Google Maps">
      <MapPreview latitude={latitude} longitude={longitude} />
      {card.name || card.address ? (
        <span className="location-card__text">
          {card.name ? <span className="location-card__name">{card.name}</span> : null}
          {card.address ? <span className="location-card__address">{card.address}</span> : null}
        </span>
      ) : null}
    </a>
  );
}

/* ---------------------------------------------------------------- Link preview */

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function LinkPreviewCard({ preview, compact = false, onRemove }) {
  const [imageFailed, setImageFailed] = useState(false);
  if (!preview) return null;
  const image = preview.image && !imageFailed ? preview.image : "";
  const body = (
    <>
      {image ? <img className="link-card__image" src={image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setImageFailed(true)} /> : null}
      <span className="link-card__body">
        {preview.title ? <span className="link-card__title">{preview.title}</span> : null}
        {preview.description ? <span className="link-card__description">{preview.description}</span> : null}
        <span className="link-card__site">{preview.site_name || hostOf(preview.url)}</span>
      </span>
    </>
  );
  if (compact) {
    return (
      <div className="link-card link-card--composer">
        {body}
        {onRemove ? (
          <button type="button" className="icon-btn link-card__remove" aria-label="Remove link preview" onClick={onRemove}>
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        ) : null}
      </div>
    );
  }
  return (
    <a className="link-card" href={preview.url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()}>
      {body}
    </a>
  );
}
