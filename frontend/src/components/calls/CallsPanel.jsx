import { useMemo, useState } from "react";
import { Phone, PhoneCall, PhoneIncoming, PhoneMissed, PhoneOutgoing, Video } from "lucide-react";
import { useStore } from "../../store/store";
import { duration as formatDuration, listTime } from "../../utils/format";
import { contactsByUser, displayUserName, roomTitle } from "../../utils/messages";
import { Avatar, EmptyState, IconButton, PanelHeader, SearchInput } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { useCalls } from "./callContext";
import NewCallDialog from "./NewCallDialog";

function callPeer(call, me) {
  if (Number(call.caller?.id) !== Number(me.id)) return call.caller;
  return call.participants?.map((p) => p.user).find((user) => Number(user?.id) !== Number(me.id)) || null;
}

export default function CallsPanel() {
  const app = useApp();
  const { startCall } = useCalls();
  const calls = useStore((state) => state.calls);
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const [query, setQuery] = useState("");
  const [newCall, setNewCall] = useState(false);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);

  const favorites = useMemo(
    () => Object.values(rooms).filter((room) => room.isFavorite && !room.isGroup && room.otherUser).slice(0, 8),
    [rooms],
  );

  const rows = useMemo(() => {
    const term = query.trim().toLowerCase();
    return calls
      .map((call) => {
        const room = rooms[call.room];
        const peer = callPeer(call, me);
        const name = room ? roomTitle(room, contactMap, me) : peer ? displayUserName(peer, contactMap) : "Unknown";
        return { call, room, peer, name };
      })
      .filter(({ name }) => !term || name.toLowerCase().includes(term));
  }, [calls, rooms, contactMap, me, query]);

  return (
    <section className="panel calls-panel">
      <PanelHeader
        title="Calls"
        actions={
          app.compact ? null : <IconButton icon={PhoneCall} label="New call" onClick={() => setNewCall(true)} />
        }
      />
      <SearchInput value={query} onChange={setQuery} placeholder="Search name or number" />
      <div className="panel__scroll">
        {favorites.length && !query ? (
          <>
            <div className="section-label section-label--plain">Favorites</div>
            <div className="list-pad">
              {favorites.map((room) => {
                const title = roomTitle(room, contactMap, me);
                return (
                  <div key={room.id} className="row row--static">
                    <Avatar src={room.otherUser?.profile?.profile_picture} name={title} />
                    <span className="row__body"><span className="row__title">{title}</span></span>
                    <IconButton icon={Video} label={`Video call ${title}`} onClick={() => startCall(room, "video")} />
                    <IconButton icon={Phone} label={`Voice call ${title}`} onClick={() => startCall(room, "audio")} />
                  </div>
                );
              })}
            </div>
          </>
        ) : null}

        <div className="section-label section-label--plain">Recent</div>
        {!rows.length ? <EmptyState icon={Phone} title="No calls yet" text="Voice and video calls you make or receive appear here." /> : null}
        <div className="list-pad">
          {rows.map(({ call, room, peer, name }) => {
            const outgoing = Number(call.caller?.id) === Number(me.id);
            const missed = call.is_missed;
            const joinedCount = call.is_group ? (call.participants || []).filter((p) => p.answered_at).length : 0;
            const Icon = missed ? PhoneMissed : outgoing ? PhoneOutgoing : PhoneIncoming;
            const label = missed ? "Missed" : outgoing ? "Outgoing" : "Incoming";
            const video = call.call_type === "VIDEO";
            return (
              <div key={call.id} className="row call-row" role="button" tabIndex={0} onClick={() => room && app.openRoom(room.id)}>
                <Avatar src={room?.isGroup ? room.groupPhoto : peer?.profile?.profile_picture} name={name} group={room?.isGroup} />
                <span className="row__body">
                  <span className={`row__title ${missed ? "is-missed" : ""}`}>{name}</span>
                  <span className={`row__subtitle call-row__sub ${missed ? "is-missed" : ""}`}>
                    <Icon size={15} /> {label}
                    {call.is_group && joinedCount > 1 ? ` · ${joinedCount} joined` : ""}
                    {call.answered_at && call.duration && !missed ? ` · ${formatDuration(call.duration)}` : ""}
                  </span>
                </span>
                <span className="call-row__time">{listTime(call.started_at)}</span>
                {room ? (
                  <IconButton
                    icon={video ? Video : Phone}
                    label={`Call ${name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      startCall(room, video ? "video" : "audio");
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      {app.compact ? (
        <div className="fab-stack">
          <button type="button" className="fab" onClick={() => setNewCall(true)} aria-label="New call">
            <PhoneCall size={24} />
          </button>
        </div>
      ) : null}
      {newCall ? <NewCallDialog onClose={() => setNewCall(false)} /> : null}
    </section>
  );
}
