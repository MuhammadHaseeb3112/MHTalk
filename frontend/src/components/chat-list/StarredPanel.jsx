import { useEffect, useMemo, useState } from "react";
import { jumpToMessage } from "../../services/jump";
import { Star } from "lucide-react";
import { errorMessage } from "../../api/client";
import { messageApi } from "../../api/endpoints";
import { useStore } from "../../store/store";
import { listTime } from "../../utils/format";
import { contactsByUser, displayUserName, previewText, roomTitle } from "../../utils/messages";
import { Avatar, EmptyState, PanelHeader, Spinner } from "../common/ui";
import { useApp } from "../layout/AppContext";

/** Starred messages across all chats (or one chat when roomId is given). */
export default function StarredPanel({ roomId }) {
  const app = useApp();
  const me = useStore((state) => state.me);
  const rooms = useStore((state) => state.rooms);
  const contacts = useStore((state) => state.contacts);
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);

  useEffect(() => {
    messageApi
      .starred()
      .then((rows) => setItems(roomId ? rows.filter((row) => Number(row.room_id) === Number(roomId)) : rows))
      .catch((err) => setError(errorMessage(err)));
  }, [roomId]);

  return (
    <section className="panel">
      <PanelHeader title="Starred messages" onBack={app.popPanel} variant="sub" />
      <div className="panel__scroll">
        {!items && !error ? <div className="list-loading"><Spinner /></div> : null}
        {error ? <EmptyState text={error} /> : null}
        {items && !items.length ? <EmptyState icon={Star} title="No starred messages" text="Tap and hold on any message to star it, so you can easily find it later." /> : null}
        <div className="list-pad">
          {items?.map((message) => {
            const room = rooms[message.room_id];
            return (
              <button
                key={message.id}
                type="button"
                className="row row--starred"
                onClick={() => {
                  if (!room) return;
                  app.openRoom(room.id);
                  jumpToMessage(room.id, message.id);
                }}
              >
                <Avatar src={message.sender?.profile?.profile_picture} name={displayUserName(message.sender, contactMap, { me })} size={40} />
                <span className="row__body">
                  <span className="row__title">
                    {displayUserName(message.sender, contactMap, { me })}
                    {room ? <span className="row__context"> ▸ {roomTitle(room, contactMap, me)}</span> : null}
                    <span className="row__time">{listTime(message.created_at)}</span>
                  </span>
                  <span className="row__subtitle row__subtitle--wrap">
                    <Star size={12} className="star-inline" /> {previewText(message, me?.id)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
