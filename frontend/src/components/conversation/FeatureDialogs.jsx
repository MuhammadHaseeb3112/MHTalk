import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LocateFixed, Radio, Timer, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { messageApi } from "../../api/endpoints";
import { setDisappearing } from "../../store/actions";
import { DISAPPEARING_OPTIONS, viewOnceState } from "../../utils/messages";
import { Avatar, IconButton, Modal, Spinner, Toggle } from "../common/ui";
import AudioPlayer from "../messages/AudioPlayer";
import { MapPreview, ViewOnceIcon } from "../messages/FeatureCards";

/* ---------------------------------------------------------------- Create poll */

const MAX_OPTIONS = 12;

/**
 * WhatsApp "Create poll": a question, options that grow as you type (up to
 * 12, at least 2 filled) and "Allow multiple answers".
 */
export function PollComposerDialog({ onClose, onSend }) {
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState(["", ""]);
  const [multiple, setMultiple] = useState(true);
  const listRef = useRef(null);

  const filled = options.map((option) => option.trim()).filter(Boolean);
  const duplicates = new Set(filled.map((option) => option.toLowerCase())).size !== filled.length;
  const valid = question.trim() && filled.length >= 2 && !duplicates;

  function setOption(index, value) {
    setOptions((current) => {
      const next = current.slice();
      next[index] = value;
      // Always keep one empty row at the end (until 12).
      if (index === next.length - 1 && value.trim() && next.length < MAX_OPTIONS) next.push("");
      // Collapse extra trailing empty rows.
      while (next.length > 2 && !next[next.length - 1].trim() && !next[next.length - 2].trim()) next.pop();
      return next;
    });
  }

  function onKeyDown(event, index) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const inputs = listRef.current?.querySelectorAll("input");
    inputs?.[index + 1]?.focus();
  }

  return (
    <Modal
      title="Create poll"
      onClose={onClose}
      width={460}
      className="poll-composer"
      footer={
        <button
          type="button"
          className="btn btn--primary"
          disabled={!valid}
          onClick={() => onSend({ question: question.trim(), options: filled, allow_multiple: multiple })}
        >
          Send
        </button>
      }
    >
      <label className="poll-composer__label" htmlFor="poll-question">Question</label>
      <input
        id="poll-question"
        className="line-input poll-composer__question"
        value={question}
        maxLength={255}
        placeholder="Ask question"
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => onKeyDown(event, -1)}
      />
      <span className="poll-composer__label">Options</span>
      <div className="poll-composer__options" ref={listRef}>
        {options.map((option, index) => (
          <div key={index} className="poll-composer__option">
            <input
              className="line-input"
              value={option}
              maxLength={100}
              placeholder="+ Add"
              aria-label={`Option ${index + 1}`}
              onChange={(event) => setOption(index, event.target.value)}
              onKeyDown={(event) => onKeyDown(event, index)}
            />
            {options.length > 2 && option ? (
              <IconButton icon={X} label={`Remove option ${index + 1}`} size={16} onClick={() => setOptions((current) => {
                const next = current.filter((_, i) => i !== index);
                if (next[next.length - 1]?.trim() && next.length < MAX_OPTIONS) next.push("");
                return next.length >= 2 ? next : [...next, ""];
              })} />
            ) : null}
          </div>
        ))}
      </div>
      {duplicates ? <p className="poll-composer__error">Options must be different.</p> : null}
      <div className="poll-composer__toggle">
        <span>Allow multiple answers</span>
        <Toggle checked={multiple} onChange={setMultiple} label="Allow multiple answers" />
      </div>
    </Modal>
  );
}

/* ---------------------------------------------------------------- Poll votes */

export function PollVotesDialog({ message, nameOf, userOf, onClose }) {
  const poll = message?.poll;
  if (!poll) return null;
  const options = [...poll.options].sort((a, b) => (b.count || 0) - (a.count || 0));
  const top = options[0]?.count || 0;
  return (
    <Modal title="Poll details" onClose={onClose} width={440} className="poll-votes">
      <p className="poll-votes__question">{poll.question}</p>
      <p className="poll-votes__total">{poll.total_voters} {poll.total_voters === 1 ? "person" : "people"} voted</p>
      {options.map((option) => (
        <section key={option.id} className="poll-votes__option">
          <header>
            <span className="poll-votes__text">{option.text}</span>
            <span className="poll-votes__count">
              {top && option.count === top ? "★ " : ""}
              {option.count || 0} vote{option.count === 1 ? "" : "s"}
            </span>
          </header>
          {(option.voters || []).length ? (
            <ul>
              {option.voters.map((id) => {
                const user = userOf(id);
                return (
                  <li key={id}>
                    <Avatar src={user?.profile?.profile_picture} name={nameOf(id)} size={32} />
                    <span>{nameOf(id)}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="info-muted">No votes</p>
          )}
        </section>
      ))}
    </Modal>
  );
}

/* ---------------------------------------------------------------- Location */

function geolocationError(error) {
  if (!error) return "Couldn't get your location.";
  if (error.code === 1) {
    return "Location permission is blocked. Allow location access for this site in your browser settings (the icon next to the address bar), then try again.";
  }
  if (error.code === 2) return "Your location isn't available right now. Check that location services are turned on for your device.";
  if (error.code === 3) return "Finding your location took too long. Try again.";
  return error.message || "Couldn't get your location.";
}

/** "Send your current location" using the browser's geolocation. */
const LIVE_DURATIONS = [
  { seconds: 900, label: "15 minutes" },
  { seconds: 3600, label: "1 hour" },
  { seconds: 28800, label: "8 hours" },
];

export function LocationDialog({ onClose, onSend, allowLive = true }) {
  const [state, setState] = useState({ status: "locating", position: null, error: "" });
  const [name, setName] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [liveOpen, setLiveOpen] = useState(false);
  const [liveSeconds, setLiveSeconds] = useState(3600);

  useEffect(() => {
    let cancelled = false;
    if (!window.isSecureContext || !navigator.geolocation) {
      window.setTimeout(() => !cancelled && setState({ status: "error", position: null, error: "Location sharing needs a secure (https) connection and a browser that supports it." }), 0);
      return () => {
        cancelled = true;
      };
    }
    navigator.geolocation.getCurrentPosition(
      (position) => !cancelled && setState({ status: "ready", position: position.coords, error: "" }),
      (error) => !cancelled && setState({ status: "error", position: null, error: geolocationError(error) }),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const coords = state.position;
  const phone = window.innerWidth <= 600;
  const mapSize = phone ? { width: window.innerWidth, height: Math.round(window.innerHeight * 0.4) } : { width: 392, height: 200 };
  const base = coords
    ? { latitude: coords.latitude, longitude: coords.longitude, accuracy: Number.isFinite(coords.accuracy) ? Math.round(coords.accuracy) : undefined }
    : null;
  if (liveOpen && base) {
    return (
      <Modal title="Share live location" onClose={onClose} width={440} className="location-dialog">
        <div className="location-dialog__map">
          <MapPreview latitude={base.latitude} longitude={base.longitude} width={mapSize.width} height={phone ? Math.round(mapSize.height * 0.8) : 160} />
        </div>
        <p className="location-dialog__note">Participants in this chat will see your location in real time while this chat is open on your phone.</p>
        <div className="location-dialog__durations" role="radiogroup" aria-label="Share for">
          {LIVE_DURATIONS.map((option) => (
            <button
              key={option.seconds}
              type="button"
              role="radio"
              aria-checked={liveSeconds === option.seconds}
              className={`chip ${liveSeconds === option.seconds ? "is-active" : ""}`}
              onClick={() => setLiveSeconds(option.seconds)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="location-dialog__actions">
          <button type="button" className="btn btn--outline" onClick={() => setLiveOpen(false)}>Back</button>
          <button type="button" className="btn btn--primary" onClick={() => onSend({ ...base, live_seconds: liveSeconds })}>Share</button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal title="Send location" onClose={onClose} width={440} className="location-dialog">
      {state.status === "locating" ? (
        <div className="location-dialog__status"><Spinner /> <span>Finding your location…</span></div>
      ) : null}
      {state.status === "error" ? (
        <div className="location-dialog__error" role="alert">
          <p>{state.error}</p>
          <button type="button" className="btn btn--outline" onClick={() => { setState({ status: "locating", position: null, error: "" }); setAttempt((value) => value + 1); }}>
            Try again
          </button>
        </div>
      ) : null}
      {coords ? (
        <>
          <div className="location-dialog__map">
            <MapPreview latitude={coords.latitude} longitude={coords.longitude} width={mapSize.width} height={mapSize.height} />
            <button
              type="button"
              className="location-dialog__recenter"
              aria-label="Refresh my location"
              onClick={() => { setState({ status: "locating", position: null, error: "" }); setAttempt((value) => value + 1); }}
            >
              <LocateFixed size={20} />
            </button>
          </div>
          {allowLive ? (
            <button type="button" className="location-dialog__send" onClick={() => setLiveOpen(true)}>
              <span className="location-dialog__icon location-dialog__icon--live"><Radio size={22} /></span>
              <span>
                <strong>Share live location</strong>
                <small>15 minutes, 1 hour or 8 hours</small>
              </span>
            </button>
          ) : null}
          <p className="location-dialog__section">Your location</p>
          <button
            type="button"
            className="location-dialog__send"
            onClick={() =>
              onSend({
                latitude: coords.latitude,
                longitude: coords.longitude,
                accuracy: Number.isFinite(coords.accuracy) ? Math.round(coords.accuracy) : undefined,
                name: name.trim() || undefined,
              })
            }
          >
            <span className="location-dialog__icon location-dialog__icon--ring"><LocateFixed size={22} /></span>
            <span>
              <strong>Send your current location</strong>
              <small>{Number.isFinite(coords.accuracy) ? `Accurate to ${Math.round(coords.accuracy)} metres` : ""}</small>
            </span>
          </button>
          <input
            className="line-input location-dialog__name"
            value={name}
            maxLength={120}
            placeholder="Add a place name (optional)"
            aria-label="Place name"
            onChange={(event) => setName(event.target.value)}
          />
        </>
      ) : null}
    </Modal>
  );
}

/* ---------------------------------------------------------------- Disappearing */

export function DisappearingDialog({ room, canEdit = true, onClose }) {
  const [busy, setBusy] = useState(false);
  const current = room.disappearingSeconds || 0;
  async function choose(seconds) {
    if (busy || !canEdit) return;
    setBusy(true);
    const ok = await setDisappearing(room.id, seconds);
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal title="Disappearing messages" onClose={onClose} width={440} className="disappearing-dialog">
      <div className="disappearing-dialog__hero"><Timer size={44} strokeWidth={1.4} /></div>
      <p className="modal__text">
        Make messages in this chat disappear. For more privacy and storage, all new messages will disappear from this chat for
        everyone after the selected duration.{" "}
        {room.isGroup && room.editInfoAdminsOnly ? "Only admins can change this setting." : "Anyone in the chat can change this setting."}
      </p>
      <div className="radio-list" role="radiogroup" aria-label="Message timer">
        {DISAPPEARING_OPTIONS.map((option) => (
          <label key={option.seconds} className={`radio ${current === option.seconds ? "is-checked" : ""}`}>
            <input type="radio" name="disappearing" checked={current === option.seconds} disabled={busy || !canEdit} onChange={() => choose(option.seconds)} />
            <span className="radio__dot" />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </Modal>
  );
}

/* ---------------------------------------------------------------- View once viewer */

// The server serves view once media exactly once. Share the request between
// effect re-runs (React StrictMode mounts twice in development) so a second
// run doesn't burn the only allowed download.
const viewOnceRequests = new Map();
function fetchViewOnce(id) {
  if (!viewOnceRequests.has(id)) {
    const request = messageApi.openViewOnce(id);
    viewOnceRequests.set(id, request);
    const forget = () => window.setTimeout(() => viewOnceRequests.delete(id), 4000);
    request.then(forget, forget);
  }
  return viewOnceRequests.get(id);
}

/**
 * Downloads the view once media (allowed exactly once) and shows it full
 * screen. Nothing is cached: closing the viewer revokes the object URL.
 */
export function ViewOnceViewer({ message, nameOf, onOpened, onClose }) {
  const [state, setState] = useState({ url: "", error: "", type: "" });
  const { video, voice } = viewOnceState(message);

  useEffect(() => {
    let url = "";
    let cancelled = false;
    fetchViewOnce(message.id)
      .then((blob) => {
        onOpened?.();
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setState({ url, error: "", type: blob.type });
      })
      .catch(async (error) => {
        let text = errorMessage(error, "Couldn't open this media.");
        const data = error?.response?.data;
        if (data instanceof Blob) {
          try {
            text = JSON.parse(await data.text()).detail || text;
          } catch {
            /* keep the generic text */
          }
        }
        if (error?.response?.status === 410) onOpened?.();
        if (!cancelled) setState({ url: "", error: text, type: "" });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
    // Opening is one-shot: never refetch for the same viewer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message.id]);

  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isVoice = voice || state.type.startsWith("audio/");
  const isVideo = !isVoice && (state.type ? state.type.startsWith("video/") : video);
  const noun = isVoice ? "voice message" : isVideo ? "video" : "photo";
  return createPortal(
    <div className="lightbox view-once-viewer" role="dialog" aria-label="View once media" onContextMenu={(event) => event.preventDefault()}>
      <header className="lightbox__top">
        <ViewOnceIcon size={26} />
        <div className="lightbox__who">
          <strong>{nameOf(message.sender?.id)}</strong>
          <span>View once {noun}</span>
        </div>
        <div className="lightbox__actions">
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
      </header>
      <div className="lightbox__stage" onClick={(event) => event.target === event.currentTarget && onClose()}>
        {state.error ? (
          <p className="view-once-viewer__error">{state.error}</p>
        ) : !state.url ? (
          <Spinner size={32} />
        ) : isVoice ? (
          <div className="view-once-viewer__voice">
            <AudioPlayer src={state.url} seconds={message.voice_note?.duration || 0} waveform={message.voice_note?.waveform} isVoice seed={`vo-${message.id}`} />
          </div>
        ) : isVideo ? (
          <video src={state.url} controls autoPlay playsInline controlsList="nodownload noplaybackrate" disablePictureInPicture />
        ) : (
          <img src={state.url} alt="View once" draggable={false} />
        )}
      </div>
      <p className="lightbox__caption view-once-viewer__note">This {noun} is set to view once. It will disappear when you close it.</p>
    </div>,
    document.body,
  );
}
