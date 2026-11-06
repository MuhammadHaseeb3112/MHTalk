import { useMemo } from "react";
import { ArrowLeft, MessageSquareText, Phone, PhoneIncoming, PhoneMissed, PhoneOutgoing, Video, X } from "lucide-react";
import { useStore } from "../../store/store";
import { clockTime, dayLabel } from "../../utils/format";
import { contactsByUser, displayUserName, roomTitle } from "../../utils/messages";
import { Avatar } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { useCalls } from "./callContext";

function spoken(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  const parts = [];
  if (minutes) parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);
  if (secs || !minutes) parts.push(`${secs} second${secs === 1 ? "" : "s"}`);
  return parts.join(" ");
}

function outcome(call, outgoing) {
  if (call.answered_at && call.duration) return spoken(call.duration);
  if (call.status === "REJECTED") return outgoing ? "Declined" : "You declined";
  if (call.status === "BUSY") return "Busy";
  if (call.is_missed) return "Missed";
  if (outgoing) return "No answer";
  return call.answered_at ? spoken(call.duration) : "Not answered";
}

/**
 * WhatsApp "Call info": the person with Message / Video / Voice buttons and
 * every call with them, grouped by day, with time and how long it lasted.
 */
export default function CallInfo({ roomId, peerId, day, onClose }) {
  const app = useApp();
  const { startCall } = useCalls();
  const calls = useStore((state) => state.calls);
  const room = useStore((state) => state.rooms[roomId]);
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);

  const history = useMemo(
    () =>
      calls
        .filter((call) => (roomId ? Number(call.room) === Number(roomId) : [call.caller, ...(call.participants || []).map((p) => p.user)].some((user) => Number(user?.id) === Number(peerId))))
        .filter((call) => !day || dayLabel(call.started_at) === day)
        .sort((a, b) => new Date(b.started_at) - new Date(a.started_at)),
    [calls, roomId, peerId, day],
  );
  const first = history[0];
  const peer = room?.otherUser || (first && (Number(first.caller?.id) !== Number(me.id) ? first.caller : first.participants?.map((p) => p.user).find((u) => Number(u?.id) !== Number(me.id))));
  const name = room ? roomTitle(room, contactMap, me) : peer ? displayUserName(peer, contactMap) : "Unknown";
  const photo = room?.isGroup ? room.groupPhoto : peer?.profile?.profile_picture;

  const days = [];
  history.forEach((call) => {
    const label = dayLabel(call.started_at);
    const last = days[days.length - 1];
    if (last && last.label === label) last.calls.push(call);
    else days.push({ label, calls: [call] });
  });

  return (
    <section className="call-info">
      <header className="call-info__bar">
        {app.compact ? <button type="button" className="icon-btn" aria-label="Back" onClick={onClose}><ArrowLeft size={22} /></button> : null}
        <h2>Call info</h2>
        {app.compact ? null : <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><X size={22} /></button>}
      </header>
      <div className="call-info__scroll">
        <div className="call-info__card">
          <div className="call-info__who">
            <Avatar src={photo} name={name} group={room?.isGroup} size={56} />
            <strong>{name}</strong>
            {room ? (
              <span className="call-info__actions">
                <button type="button" aria-label={`Message ${name}`} onClick={() => { app.setSection("chats"); app.openRoom(room.id); }}><MessageSquareText size={22} /></button>
                <button type="button" aria-label={`Video call ${name}`} onClick={() => startCall(room, "video")}><Video size={22} /></button>
                <button type="button" aria-label={`Voice call ${name}`} onClick={() => startCall(room, "audio")}><Phone size={22} /></button>
              </span>
            ) : null}
          </div>
          {days.map((day) => (
            <div key={day.label} className="call-info__day">
              <p className="call-info__date">{day.label}</p>
              {day.calls.map((call) => {
                const outgoing = Number(call.caller?.id) === Number(me.id);
                const video = call.call_type === "VIDEO";
                const missed = call.is_missed;
                const Icon = missed ? PhoneMissed : outgoing ? PhoneOutgoing : PhoneIncoming;
                return (
                  <div key={call.id} className={`call-info__line ${missed ? "is-missed" : ""}`}>
                    <Icon size={18} />
                    <span className="call-info__what">
                      {missed ? "Missed" : outgoing ? "Outgoing" : "Incoming"} {video ? "video" : "voice"} call at {clockTime(call.started_at)}
                    </span>
                    <span className="call-info__len">{outcome(call, outgoing)}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
