import { useCallback, useEffect, useMemo, useState } from "react";
import { errorMessage } from "../../api/client";
import { messageApi } from "../../api/endpoints";
import { useStore } from "../../store/store";
import { useTicker } from "../../hooks";
import { detailTime } from "../../utils/format";
import { contactsByUser } from "../../utils/messages";
import { Avatar, EmptyState, PanelHeader, Spinner } from "../common/ui";
import { DoubleTick } from "../common/Icons";
import { useApp } from "../layout/AppContext";
import MessageBubble from "../messages/MessageBubble";

/**
 * Message info: read by / delivered to, per recipient, from the server's
 * receipt records. Refreshes live when a receipt for this message arrives.
 */
export default function MessageInfo({ roomId, messageId }) {
  const app = useApp();
  useTicker(20000); // keeps "Just now" / "N min ago" current
  const message = useStore((state) => state.messages[roomId]?.items.find((item) => item.id === messageId));
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    messageApi
      .info(messageId)
      .then((data) => {
        setInfo(data);
        setError("");
      })
      .catch((err) => setError(errorMessage(err)));
  }, [messageId]);

  useEffect(() => {
    load();
  }, [load]);

  // Refresh live whenever any recipient receives or reads this message
  // (group members' receipts don't always change the overall ticks).
  useEffect(() => {
    let timer = null;
    const onReceipt = (event) => {
      if (Number(event.detail) !== Number(messageId)) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(load, 250); // batch bursts of receipts
    };
    window.addEventListener("mhtalk:receipt", onReceipt);
    // Safety net in case the socket was reconnecting when a receipt was sent.
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 15000);
    return () => {
      window.removeEventListener("mhtalk:receipt", onReceipt);
      window.clearTimeout(timer);
      window.clearInterval(poll);
    };
  }, [load, messageId]);

  const nameFor = (row) => contactMap.get(Number(row.user_id))?.name || row.name || row.phone_number;
  const isGroup = info?.room_type === "GROUP";
  const noop = useCallback(() => {}, []);

  return (
    <section className="panel info-panel">
      <PanelHeader title="Message info" onBack={app.closeDrawer} variant="close" />
      <div className="panel__scroll">
        {message ? (
          <div className="message-info__preview">
            <MessageBubble message={message} myId={me.id} isOwn showTail selectMode={false} selected={false} nameOf={() => "You"} colorOf={() => "var(--accent)"} onAction={noop} />
          </div>
        ) : null}
        {!info && !error ? <div className="list-loading"><Spinner /></div> : null}
        {error ? <EmptyState text={error} /> : null}
        {info ? (
          isGroup ? (
            <>
              <div className="info-section info-section--list">
                <span className="receipt-head">
                  <DoubleTick size={18} className="ticks--read" /> Read by {info.read_count ? `(${info.read_count})` : ""}
                </span>
                {info.read_by.length ? (
                  info.read_by.map((row) => (
                    <div key={row.user_id} className="row row--static">
                      <Avatar src={row.profile_picture} name={nameFor(row)} size={40} />
                      <span className="row__body">
                        <span className="row__title">{nameFor(row)}</span>
                        <span className="row__subtitle">{detailTime(row.read_at)}</span>
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="info-muted info-pad">Not read yet</p>
                )}
              </div>
              <div className="info-section info-section--list">
                <span className="receipt-head">
                  <DoubleTick size={18} /> Delivered to {info.delivered_count ? `(${info.delivered_count})` : ""}
                </span>
                {info.delivered_to.filter((row) => !row.read_at).length ? (
                  info.delivered_to
                    .filter((row) => !row.read_at)
                    .map((row) => (
                      <div key={row.user_id} className="row row--static">
                        <Avatar src={row.profile_picture} name={nameFor(row)} size={40} />
                        <span className="row__body">
                          <span className="row__title">{nameFor(row)}</span>
                          <span className="row__subtitle">{detailTime(row.delivered_at)}</span>
                        </span>
                      </div>
                    ))
                ) : (
                  <p className="info-muted info-pad">{info.read_count ? "Everyone who received it has read it" : "Not delivered yet"}</p>
                )}
              </div>
              {info.pending.length ? (
                <div className="info-section info-section--list">
                  <span className="receipt-head">Waiting ({info.pending.length})</span>
                  {info.pending.map((row) => (
                    <div key={row.user_id} className="row row--static">
                      <Avatar src={row.profile_picture} name={nameFor(row)} size={40} />
                      <span className="row__body"><span className="row__title">{nameFor(row)}</span></span>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div className="info-section">
              {(() => {
                const row = info.recipients[0];
                return (
                  <>
                    <div className="receipt-line">
                      <DoubleTick size={18} className="ticks--read" />
                      <span>
                        <strong>Read</strong>
                        <span>{row?.read_at ? detailTime(row.read_at) : "—"}</span>
                      </span>
                    </div>
                    <div className="receipt-line">
                      <DoubleTick size={18} />
                      <span>
                        <strong>Delivered</strong>
                        <span>{row?.delivered_at ? detailTime(row.delivered_at) : "—"}</span>
                      </span>
                    </div>
                    <p className="info-muted">Sent {detailTime(info.sent_at)}</p>
                  </>
                );
              })()}
            </div>
          )
        ) : null}
      </div>
    </section>
  );
}
