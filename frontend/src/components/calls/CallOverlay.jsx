import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Maximize2,
  Mic,
  MicOff,
  Minimize2,
  MonitorUp,
  Phone,
  PhoneOff,
  Repeat,
  SwitchCamera,
  Volume2,
  ScreenShareOff,
  Smile,
  Video,
  VideoOff,
  X,
} from "lucide-react";
import { useStore } from "../../store/store";
import { duration as formatDuration } from "../../utils/format";
import { contactsByUser, displayUserName, roomTitle } from "../../utils/messages";
import { Avatar } from "../common/ui";
import GroupCallScreen, { GroupCallAudio } from "./GroupCallScreen";

// Phone browsers (Chrome Android, Safari iOS) don't let websites share the
// screen, only desktop browsers do.
const canShareScreen = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getDisplayMedia) && !/Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

const CALL_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];
const CORNERS = ["br", "bl", "tr", "tl"];

function MediaView({ stream, className = "", mirrored, fit = "cover" }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.srcObject !== stream) ref.current.srcObject = stream || null;
  }, [stream]);
  // Always muted: the other person's audio plays through one <audio> element.
  return <video ref={ref} className={`call-video call-video--${fit} ${className} ${mirrored ? "is-mirrored" : ""}`} autoPlay playsInline muted />;
}

/** A call tile for someone whose camera is off: their picture, like WhatsApp. */
function CameraOffTile({ name, photo }) {
  return (
    <div className="call-tile-off">
      <Avatar src={photo} name={name} size={96} />
      <span><VideoOff size={14} /> Camera off</span>
    </div>
  );
}

/** Small draggable preview: click to swap with the big view, drag to another corner. */
function PictureInPicture({ corner, onCorner, onSwap, children, label, action = null }) {
  const drag = useRef(null);
  const [offset, setOffset] = useState(null);
  return (
    <div
      className={`call-pip call-pip--${corner} ${offset ? "is-dragging" : ""}`}
      style={offset ? { transform: `translate(${offset.dx}px, ${offset.dy}px)` } : undefined}
      role="button"
      tabIndex={0}
      aria-label={label}
      title="Click to swap · drag to move"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        drag.current = { x: event.clientX, y: event.clientY, moved: false };
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const dx = event.clientX - drag.current.x;
        const dy = event.clientY - drag.current.y;
        if (!drag.current.moved && Math.hypot(dx, dy) < 6) return;
        drag.current.moved = true;
        setOffset({ dx, dy });
      }}
      onPointerUp={(event) => {
        const state = drag.current;
        drag.current = null;
        setOffset(null);
        if (!state) return;
        if (!state.moved) {
          onSwap();
          return;
        }
        const left = event.clientX < window.innerWidth / 2;
        const top = event.clientY < window.innerHeight / 2;
        onCorner(`${top ? "t" : "b"}${left ? "l" : "r"}`);
      }}
      onPointerCancel={() => {
        drag.current = null;
        setOffset(null);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSwap();
        }
      }}
    >
      {children}
      {action || <span className="call-pip__hint"><Repeat size={14} /></span>}
    </div>
  );
}

/** WhatsApp Web-style incoming call card (bottom-left, doesn't block the app). */
function IncomingCard({ call, name, photo, subtitle, onAccept, onDecline, onDismiss }) {
  const isVideo = call.type === "video";
  return createPortal(
    <div className="call-incoming" role="alertdialog" aria-label={`Incoming ${call.group ? "group " : ""}${isVideo ? "video" : "voice"} call from ${name}`}>
      <div className="call-incoming__top">
        <Avatar src={photo} name={name} size={48} group={call.group} />
        <div className="call-incoming__who">
          <strong>{name}</strong>
          <span>{subtitle || (isVideo ? "Incoming video call" : "Incoming voice call")}</span>
        </div>
        <button type="button" className="icon-btn" onClick={onDismiss} aria-label="Dismiss" title="Hide (keeps ringing for the caller)">
          <X size={20} />
        </button>
      </div>
      <div className="call-incoming__actions">
        <button type="button" className="call-pill call-pill--decline" onClick={onDecline} aria-label="Decline">
          <PhoneOff size={18} /> Decline
        </button>
        <button type="button" className="call-pill call-pill--accept" onClick={onAccept} aria-label="Accept">
          {isVideo ? <Video size={18} /> : <Phone size={18} />} Accept
        </button>
      </div>
    </div>,
    document.body,
  );
}

/**
 * Minimized 1:1 call, like WhatsApp: a small floating window with the other
 * person's video (or photo) that you can drag anywhere; tap it to go back.
 */
function FloatingCall({ call, name, photo, status, remoteStream, remoteVideoOn, onExpand, onHangUp, onToggleMute }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [pos, setPos] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem("mhtalk_float_pos") || "null");
    } catch {
      return null;
    }
  });
  const clamp = (x, y) => {
    const box = ref.current?.getBoundingClientRect();
    const w = box?.width || 180;
    const h = box?.height || 240;
    return { x: Math.min(Math.max(8, x), window.innerWidth - w - 8), y: Math.min(Math.max(8, y), window.innerHeight - h - 8) };
  };
  useEffect(() => {
    const onResize = () => setPos((current) => (current ? clamp(current.x, current.y) : current));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return createPortal(
    <div
      ref={ref}
      className={`call-float ${remoteVideoOn ? "has-video" : ""}`}
      style={pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : undefined}
      role="region"
      aria-label={`Call with ${name}. Drag to move, tap to open.`}
      onPointerDown={(event) => {
        if (event.target.closest("button")) return;
        const box = ref.current.getBoundingClientRect();
        drag.current = { dx: event.clientX - box.left, dy: event.clientY - box.top, x: event.clientX, y: event.clientY, moved: false };
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        const state = drag.current;
        if (!state) return;
        if (!state.moved && Math.hypot(event.clientX - state.x, event.clientY - state.y) < 6) return;
        state.moved = true;
        setPos(clamp(event.clientX - state.dx, event.clientY - state.dy));
      }}
      onPointerUp={() => {
        const state = drag.current;
        drag.current = null;
        if (!state) return;
        if (!state.moved) onExpand();
        else {
          try {
            sessionStorage.setItem("mhtalk_float_pos", JSON.stringify(ref.current ? { x: ref.current.offsetLeft, y: ref.current.offsetTop } : pos));
          } catch {
            /* ignore */
          }
        }
      }}
      onPointerCancel={() => {
        drag.current = null;
      }}
    >
      {remoteVideoOn ? (
        <MediaView stream={remoteStream} className="call-float__video" />
      ) : (
        <div className="call-float__who">
          <Avatar src={photo} name={name} size={64} />
        </div>
      )}
      <div className="call-float__info">
        <strong>{name}</strong>
        <span>{status}</span>
      </div>
      {call.phase !== "ended" ? (
        <div className="call-float__actions">
          <button type="button" className={`call-mini__btn ${call.muted ? "is-off" : ""}`} onClick={onToggleMute} aria-label={call.muted ? "Unmute" : "Mute"}>
            {call.muted ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button type="button" className="call-mini__btn" onClick={onExpand} aria-label="Back to call">
            <Maximize2 size={16} />
          </button>
          <button type="button" className="call-mini__btn call-mini__btn--end" onClick={onHangUp} aria-label="End call">
            <PhoneOff size={16} />
          </button>
        </div>
      ) : null}
    </div>,
    document.body,
  );
}

/** Minimized group call: a small bar so you can keep chatting during the call. */
function MiniCall({ call, name, photo, status, onExpand, onHangUp, onToggleMute }) {
  return createPortal(
    <div className="call-mini" role="region" aria-label={`Call with ${name}`}>
      <Avatar src={photo} name={name} size={40} group={call.group} />
      <button type="button" className="call-mini__who" onClick={onExpand} title="Back to call">
        <strong>{name}</strong>
        <span>{status}</span>
      </button>
      {call.phase !== "ended" ? (
        <>
          <button type="button" className={`call-mini__btn ${call.muted ? "is-off" : ""}`} onClick={onToggleMute} aria-label={call.muted ? "Unmute" : "Mute"}>
            {call.muted ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <button type="button" className="call-mini__btn" onClick={onExpand} aria-label="Back to call">
            <Maximize2 size={18} />
          </button>
          <button type="button" className="call-mini__btn call-mini__btn--end" onClick={onHangUp} aria-label="End call">
            <PhoneOff size={18} />
          </button>
        </>
      ) : null}
    </div>,
    document.body,
  );
}

/** Calls: incoming card, minimized bar, or the full call screen. */
export default function CallOverlay({
  call,
  localStream,
  remoteStream,
  remoteStreams = {},
  shareStream,
  reactions = [],
  onAccept,
  onDecline,
  onDismiss,
  onHangUp,
  onToggleMute,
  onToggleCamera,
  onSwitchCamera = null,
  onRejoin,
  onToggleShare,
  onReact,
  onToggleMinimized,
}) {
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const me = useStore((state) => state.me);
  const room = useStore((state) => (call.group ? state.rooms[call.roomId] : null));

  // Group calls: the group's name and photo, and everyone's display name.
  const people = useMemo(() => {
    if (!call.group) return [];
    const users = Object.fromEntries((room?.participants || []).map((p) => [Number(p.user?.id), p.user]));
    return Object.entries(call.members || {}).map(([id, member]) => {
      const user = users[Number(id)];
      return { ...member, id: Number(id), name: user ? displayUserName(user, contactMap) : "Unknown", photo: user?.profile?.profile_picture };
    });
  }, [call.group, call.members, room?.participants, contactMap]);
  const name = call.group ? (room ? roomTitle(room, contactMap, me) : "Group call") : displayUserName(call.peerUser, contactMap) || "Unknown";
  const photo = call.group ? room?.groupPhoto : call.peerUser?.profile?.profile_picture;
  const callerName = call.group ? displayUserName(call.peerUser, contactMap) : "";
  const [now, setNow] = useState(() => Date.now());
  const [swapped, setSwapped] = useState(false);
  const [corner, setCorner] = useState(CORNERS[0]);
  const [fullscreen, setFullscreen] = useState(false);
  const [picker, setPicker] = useState(false);
  const rootRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const [soundBlocked, setSoundBlocked] = useState(false);

  const ticking = call.phase === "ongoing" && Boolean(call.connectedAt);
  useEffect(() => {
    if (!ticking) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);

  useEffect(() => {
    if (remoteAudioRef.current && remoteStream) {
      remoteAudioRef.current.srcObject = remoteStream;
      // Browsers block sound until the page was clicked once (e.g. right
      // after a reload): then offer a button that turns it on.
      remoteAudioRef.current
        .play?.()
        .then(() => setSoundBlocked(false))
        .catch((error) => setSoundBlocked(error?.name === "NotAllowedError"));
    }
  }, [remoteStream, call.minimized, call.phase]);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    };
  }, []);

  const status =
    call.group && call.phase === "outgoing"
      ? "Ringing…"
      : call.phase === "ongoing" && call.connectedAt
      ? formatDuration((now - call.connectedAt) / 1000)
      : call.phase === "ended"
        ? call.message || "Call ended"
        : call.phase === "connecting"
          ? "Connecting…"
          : call.status;

  // The remote audio element(s) must exist in every layout.
  const audio = call.group ? <GroupCallAudio remoteStreams={remoteStreams} /> : <audio ref={remoteAudioRef} autoPlay />;

  if (call.phase === "incoming") {
    const subtitle = call.group ? `${callerName ? `${callerName} · ` : ""}Incoming group ${call.type === "video" ? "video" : "voice"} call` : "";
    return (
      <>
        {audio}
        <IncomingCard call={call} name={name} photo={photo} subtitle={subtitle} onAccept={onAccept} onDecline={onDecline} onDismiss={onDismiss} />
      </>
    );
  }

  if (call.phase === "rejoin") {
    return createPortal(
      <div className="call-incoming" role="alertdialog" aria-label={`Ongoing call with ${name}`}>
        <div className="call-incoming__top">
          <Avatar src={photo} name={name} size={48} />
          <div className="call-incoming__who">
            <strong>{name}</strong>
            <span>{call.status} · the page was reloaded</span>
          </div>
        </div>
        <div className="call-incoming__actions">
          <button type="button" className="call-pill call-pill--decline" onClick={onHangUp} aria-label="End call">
            <PhoneOff size={18} /> End
          </button>
          <button type="button" className="call-pill call-pill--accept" onClick={onRejoin} aria-label="Rejoin call">
            {call.type === "video" ? <Video size={18} /> : <Phone size={18} />} Rejoin
          </button>
        </div>
      </div>,
      document.body,
    );
  }

  if (call.minimized) {
    return (
      <>
        {audio}
        {call.group ? (
          <MiniCall call={call} name={name} photo={photo} status={status} onExpand={onToggleMinimized} onHangUp={onHangUp} onToggleMute={onToggleMute} />
        ) : (
          <FloatingCall
            call={call}
            name={name}
            photo={photo}
            status={status}
            remoteStream={remoteStream}
            remoteVideoOn={Boolean(remoteStream?.getVideoTracks().some((track) => track.readyState === "live")) && (!call.remoteCameraOff || call.remoteSharing)}
            onExpand={onToggleMinimized}
            onHangUp={onHangUp}
            onToggleMute={onToggleMute}
          />
        )}
      </>
    );
  }

  const myVideoOn = Boolean(localStream?.getVideoTracks().length) && !call.cameraOff;
  const remoteVideoOn = Boolean(remoteStream?.getVideoTracks().length) && (!call.remoteCameraOff || call.remoteSharing);
  const connected = call.phase === "ongoing" && (!call.group || people.some((person) => person.state === "joined"));

  const myTile = shareStream ? (
    <MediaView stream={shareStream} fit="contain" />
  ) : myVideoOn ? (
    <MediaView stream={localStream} mirrored={call.facing !== "environment"} />
  ) : null;
  const remoteTile = remoteVideoOn ? <MediaView stream={remoteStream} fit="contain" /> : null;

  // Big view: the other person when their video is on (click the small one to swap).
  let main = null;
  let pip = null;
  const faceTiles = connected && !call.group && (call.type === "video" || myTile || remoteTile);
  if (faceTiles) {
    // WhatsApp: in a video call both people keep a tile even with the camera
    // off (their picture shows instead), and tapping the small one swaps.
    const myFace = myTile || <CameraOffTile name={me?.display_name || "You"} photo={me?.profile?.profile_picture} />;
    const remoteFace = remoteTile || <CameraOffTile name={name} photo={photo} />;
    main = swapped ? myFace : remoteFace;
    pip = swapped ? remoteFace : myFace;
  } else if (connected && remoteTile && myTile) {
    main = swapped ? myTile : remoteTile;
    pip = swapped ? remoteTile : myTile;
  } else if (connected && remoteTile) {
    main = remoteTile;
  } else if (myTile) {
    if (connected) pip = myTile;
    else main = myTile; // still ringing: your own preview
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    else rootRef.current?.requestFullscreen?.().catch(() => {});
  }

  const ringingPreview = !connected && main;

  const controls =
    call.phase !== "ended" ? (
        <div className="call-bar">
          <div className="call-bar__group">
            <button
              type="button"
              className={`call-pill call-pill--toggle ${myVideoOn ? "is-on" : ""}`}
              onClick={onToggleCamera}
              aria-label={myVideoOn ? "Turn camera off" : "Turn camera on"}
              title={myVideoOn ? "Turn camera off" : "Turn camera on"}
            >
              {myVideoOn ? <Video size={22} /> : <VideoOff size={22} />}
            </button>
            <button
              type="button"
              className={`call-pill call-pill--toggle ${call.muted ? "" : "is-on"}`}
              onClick={onToggleMute}
              aria-label={call.muted ? "Unmute" : "Mute"}
              title={call.muted ? "Unmute" : "Mute"}
            >
              {call.muted ? <MicOff size={22} /> : <Mic size={22} />}
            </button>
            {onSwitchCamera && myVideoOn && !call.sharing ? (
              <button type="button" className="call-pill call-pill--toggle is-on" onClick={onSwitchCamera} aria-label="Switch camera" title="Switch camera (front / back)">
                <SwitchCamera size={22} />
              </button>
            ) : null}
          </div>

          <div className="call-bar__group call-bar__group--center">
            <div className="call-bar__react">
              <button type="button" className={`call-icon ${picker ? "is-active" : ""}`} onClick={() => setPicker((value) => !value)} aria-label="Send a reaction" title="React" disabled={!connected}>
                <Smile size={24} />
              </button>
              {picker ? (
                <div className="call-bar__picker" role="menu">
                  {CALL_REACTIONS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      onClick={() => {
                        onReact(emoji);
                        setPicker(false);
                      }}
                      aria-label={`React ${emoji}`}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            {canShareScreen ? <button
              type="button"
              className={`call-icon ${call.sharing ? "is-active" : ""}`}
              onClick={onToggleShare}
              aria-label={call.sharing ? "Stop sharing" : "Share screen"}
              title={call.sharing ? "Stop sharing" : "Share screen"}
              disabled={!connected}
            >
              {call.sharing ? <ScreenShareOff size={24} /> : <MonitorUp size={24} />}
            </button> : null}
          </div>

          <div className="call-bar__group call-bar__group--right">
            <button type="button" className="call-icon" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit full screen" : "Full screen"} title={fullscreen ? "Exit full screen" : "Full screen"}>
              {fullscreen ? <Minimize2 size={22} /> : <Maximize2 size={22} />}
            </button>
            <button type="button" className="call-icon" onClick={onToggleMinimized} aria-label="Minimize call" title="Minimize — keep chatting">
              <span className="call-icon__min" aria-hidden="true" />
            </button>
            <button type="button" className="call-pill call-pill--end" onClick={onHangUp} aria-label={call.group ? "Leave call" : "End call"} title={call.group ? "Leave call" : "End call"}>
              <PhoneOff size={22} />
            </button>
          </div>
        </div>
      ) : null;

  if (call.group) {
    return createPortal(
      <>
        {audio}
        <GroupCallScreen
          call={call}
          title={name}
          groupPhoto={photo}
          people={people}
          me={me}
          localStream={localStream}
          remoteStreams={remoteStreams}
          shareStream={shareStream}
          status={status}
          reactions={reactions}
          controls={controls}
          rootRef={rootRef}
          onDoubleClick={toggleFullscreen}
        />
      </>,
      document.body,
    );
  }

  return createPortal(
    <div ref={rootRef} className={`call-screen ${main && !ringingPreview ? "has-video" : ""}`} role="dialog" aria-label={`Call with ${name}`}>
      {audio}

      {soundBlocked ? (
        <button
          type="button"
          className="call-screen__sound"
          onClick={() => {
            remoteAudioRef.current?.play?.().then(() => setSoundBlocked(false)).catch(() => {});
          }}
        >
          <Volume2 size={18} /> Tap to turn on sound
        </button>
      ) : null}

      {call.remoteMuted ? (
        <span className="call-screen__badge" title={`${name} is muted`}>
          <MicOff size={18} />
        </span>
      ) : null}

      <div className="call-screen__stage" onDoubleClick={toggleFullscreen}>
        {main && !ringingPreview ? (
          <div className="call-screen__main">
            {main}
            <div className="call-screen__label">
              <strong>{faceTiles && swapped ? "You" : name}</strong>
              <span>{call.remoteSharing ? `${status} · presenting` : status}</span>
            </div>
          </div>
        ) : (
          <div className={`call-screen__center ${ringingPreview ? "is-ringing-video" : ""}`}>
            <Avatar src={call.peerUser?.profile?.profile_picture} name={name} size={ringingPreview ? 72 : 160} />
            <h2>{name}</h2>
            <p>{status}</p>
            {call.warning ? <p className="call-screen__warning">{call.warning}</p> : null}
            {ringingPreview ? <div className="call-screen__preview">{main}</div> : null}
          </div>
        )}
        {pip ? (
          <PictureInPicture
            corner={corner}
            onCorner={setCorner}
            onSwap={() => setSwapped((value) => !value)}
            label="Swap videos"
            action={
              onSwitchCamera && !swapped && myVideoOn && !shareStream ? (
                <button
                  type="button"
                  className="call-pip__switch"
                  aria-label="Switch camera"
                  title="Switch camera"
                  onPointerDown={(event) => event.stopPropagation()}
                  onPointerUp={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSwitchCamera();
                  }}
                >
                  <SwitchCamera size={18} />
                </button>
              ) : null
            }
          >
            {pip}
          </PictureInPicture>
        ) : null}
        <div className="call-reactions" aria-live="polite">
          {reactions.map((item) => (
            <span key={item.id} className={`call-reaction ${item.mine ? "is-mine" : ""}`} style={{ left: `${item.left}%` }}>
              {item.emoji}
            </span>
          ))}
        </div>
      </div>

      {controls}
    </div>,
    document.body,
  );
}
