import { useEffect, useMemo, useRef, useState } from "react";
import { MicOff, MonitorUp, Users, X } from "lucide-react";
import { profileName } from "../../utils/messages";
import { Avatar } from "../common/ui";

/**
 * WhatsApp-style group call screen: header (group, people, duration), a grid
 * of participant tiles and the shared control bar. Tiles show live video
 * when the camera is on, otherwise the avatar; a green ring marks whoever is
 * speaking (WebAudio level), and people still ringing / connecting say so.
 */

const SPEAKING_LEVEL = 0.035; // RMS of the waveform (0..1)
const SPEAKING_HOLD_MS = 450;

/** Ids of the streams whose audio level is above the speaking threshold. */
function useSpeaking(entries) {
  const [speaking, setSpeaking] = useState(() => new Set());
  const entriesRef = useRef(entries);
  useEffect(() => {
    entriesRef.current = entries;
  });
  const key = entries.map(([id, stream]) => `${id}:${stream?.id || ""}:${stream?.getAudioTracks().length || 0}`).join("|");

  useEffect(() => {
    const withAudio = entriesRef.current.filter(([, stream]) => stream?.getAudioTracks().length);
    if (!withAudio.length) return undefined;
    let context;
    try {
      context = new (window.AudioContext || window.webkitAudioContext)();
    } catch {
      return undefined;
    }
    context.resume?.().catch(() => {});
    const meters = withAudio.map(([id, stream]) => {
      const source = context.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      return { id, analyser, buffer: new Uint8Array(analyser.fftSize) };
    });
    const until = {};
    const timer = window.setInterval(() => {
      const now = Date.now();
      const next = new Set();
      meters.forEach(({ id, analyser, buffer }) => {
        analyser.getByteTimeDomainData(buffer);
        let sum = 0;
        for (let index = 0; index < buffer.length; index += 1) {
          const value = (buffer[index] - 128) / 128;
          sum += value * value;
        }
        if (Math.sqrt(sum / buffer.length) > SPEAKING_LEVEL) until[id] = now + SPEAKING_HOLD_MS;
        if ((until[id] || 0) > now) next.add(id);
      });
      setSpeaking((previous) => (previous.size === next.size && [...next].every((id) => previous.has(id)) ? previous : next));
    }, 150);
    return () => {
      window.clearInterval(timer);
      context.close().catch(() => {});
    };
  }, [key]);

  return speaking;
}

/** True while the stream has a video track that is actually receiving frames. */
function useLiveVideo(stream) {
  const [, force] = useState(0);
  const track = stream?.getVideoTracks()[0];
  useEffect(() => {
    if (!track) return undefined;
    const update = () => force((value) => value + 1);
    track.addEventListener("mute", update);
    track.addEventListener("unmute", update);
    track.addEventListener("ended", update);
    return () => {
      track.removeEventListener("mute", update);
      track.removeEventListener("unmute", update);
      track.removeEventListener("ended", update);
    };
  }, [track]);
  return Boolean(track && track.readyState === "live" && !track.muted);
}

function TileVideo({ stream, mirrored, contain }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.srcObject !== stream) ref.current.srcObject = stream || null;
  }, [stream]);
  // Muted: audio plays through the hidden <audio> elements (GroupCallAudio).
  return <video ref={ref} className={`call-video call-video--${contain ? "contain" : "cover"} ${mirrored ? "is-mirrored" : ""}`} autoPlay playsInline muted />;
}

function Tile({ tile, speaking }) {
  const live = useLiveVideo(tile.stream);
  const showVideo = tile.stream && (tile.local ? tile.videoOn : live && (tile.sharing || !tile.cameraOff));
  return (
    <div className={`gcall-tile ${speaking ? "is-speaking" : ""} ${showVideo ? "has-video" : ""}`} data-user={tile.id} aria-label={tile.name}>
      {showVideo ? (
        <TileVideo stream={tile.stream} mirrored={tile.local && !tile.sharing} contain={tile.sharing} />
      ) : (
        <div className="gcall-tile__center">
          <Avatar src={tile.photo} name={tile.avatarName || tile.name} size={tile.compact ? 64 : 88} />
          {tile.status ? <span className="gcall-tile__status">{tile.status}</span> : null}
        </div>
      )}
      <div className="gcall-tile__label">
        {tile.muted ? <MicOff size={15} aria-label="Muted" /> : null}
        {tile.sharing ? <MonitorUp size={15} aria-label="Presenting" /> : null}
        <span>{tile.name}</span>
      </div>
      {showVideo && tile.status ? <span className="gcall-tile__badge">{tile.status}</span> : null}
    </div>
  );
}

/** One hidden <audio> per remote participant (every layout, incl. minimized). */
export function GroupCallAudio({ remoteStreams }) {
  return Object.entries(remoteStreams).map(([id, stream]) => <RemoteAudio key={id} stream={stream} />);
}

function RemoteAudio({ stream }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.srcObject !== stream) {
      ref.current.srcObject = stream;
      ref.current.play?.().catch(() => {});
    }
  }, [stream]);
  return <audio ref={ref} autoPlay />;
}

const SHEET_SECTIONS = [
  ["joined", "In call"],
  ["ringing", "Ringing"],
  ["declined", "Declined"],
  ["missed", "No answer"],
  ["left", "Left"],
];

function ParticipantSheet({ people, onClose }) {
  return (
    <div className="gcall-sheet" role="dialog" aria-label="Participants">
      <div className="gcall-sheet__head">
        <strong>Participants</strong>
        <button type="button" className="call-icon" onClick={onClose} aria-label="Close participants">
          <X size={20} />
        </button>
      </div>
      <div className="gcall-sheet__list">
        {SHEET_SECTIONS.map(([state, label]) => {
          const rows = people.filter((person) => person.state === state);
          if (!rows.length) return null;
          return (
            <section key={state}>
              <h4>
                {label} · {rows.length}
              </h4>
              {rows.map((person) => (
                <div key={person.id} className="gcall-sheet__row">
                  <Avatar src={person.photo} name={person.avatarName || person.name} size={40} />
                  <span className="gcall-sheet__name">{person.name}</span>
                  {person.muted && state === "joined" ? <MicOff size={16} aria-label="Muted" /> : null}
                </div>
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default function GroupCallScreen({ call, title, groupPhoto, people, me, localStream, remoteStreams, shareStream, status, controls, reactions, rootRef, onDoubleClick }) {
  const [sheet, setSheet] = useState(false);
  const myVideoOn = Boolean(localStream?.getVideoTracks().length) && !call.cameraOff;

  // Tiles: everyone in the call or still being rung; you last (like WhatsApp).
  const tiles = useMemo(() => {
    const others = people
      .filter((person) => person.state === "joined" || person.state === "ringing")
      .map((person) => ({
        ...person,
        stream: remoteStreams[person.id] || null,
        status: person.state === "ringing" ? "Ringing…" : person.failed ? "Couldn't connect" : !person.connected ? "Connecting…" : "",
      }));
    const mine = {
      id: Number(me.id),
      local: true,
      name: "You",
      avatarName: profileName(me) || me.phone_number,
      photo: me.profile?.profile_picture,
      muted: call.muted,
      sharing: Boolean(shareStream),
      videoOn: Boolean(shareStream) || myVideoOn,
      stream: shareStream || localStream,
      status: "",
    };
    return [...others, mine];
  }, [people, remoteStreams, me, call.muted, shareStream, myVideoOn, localStream]);

  const speakingEntries = useMemo(
    () => tiles.filter((tile) => tile.stream && !tile.muted && (tile.local ? !shareStream : true)).map((tile) => [tile.id, tile.local ? localStream : tile.stream]),
    [tiles, shareStream, localStream],
  );
  const speaking = useSpeaking(speakingEntries);

  const count = tiles.length;
  const layout = count <= 1 ? "1" : count === 2 ? "2" : count <= 4 ? String(count) : "many";
  const inCall = people.filter((person) => person.state === "joined").length + 1;

  return (
    <div ref={rootRef} className="call-screen gcall" role="dialog" aria-label={`Group call: ${title}`}>
      <header className="gcall__head">
        <Avatar src={groupPhoto} name={title} group size={40} />
        <div className="gcall__title">
          <strong>{title}</strong>
          <span>
            {inCall} {inCall === 1 ? "participant" : "participants"} · {status}
          </span>
        </div>
        <button type="button" className={`call-icon ${sheet ? "is-active" : ""}`} onClick={() => setSheet((value) => !value)} aria-label="Participants" title="Participants">
          <Users size={22} />
        </button>
      </header>
      {call.warning ? <p className="call-screen__warning gcall__warning">{call.warning}</p> : null}

      <div className="gcall__stage" onDoubleClick={onDoubleClick}>
        <div className={`gcall__grid gcall__grid--${layout}`}>
          {tiles.map((tile) => (
            <Tile key={tile.id} tile={{ ...tile, compact: count > 4 }} speaking={speaking.has(tile.id)} />
          ))}
        </div>
        <div className="call-reactions" aria-live="polite">
          {reactions.map((item) => (
            <span key={item.id} className={`call-reaction ${item.mine ? "is-mine" : ""}`} style={{ left: `${item.left}%` }}>
              {item.emoji}
            </span>
          ))}
        </div>
        {sheet ? <ParticipantSheet people={[{ id: Number(me.id), name: "You", avatarName: profileName(me) || me.phone_number, photo: me.profile?.profile_picture, state: "joined", muted: call.muted }, ...people]} onClose={() => setSheet(false)} /> : null}
      </div>
      {controls}
    </div>
  );
}
