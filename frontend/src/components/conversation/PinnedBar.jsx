import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ArrowRight, Pin, PinOff } from "lucide-react";
import { chatApi } from "../../api/endpoints";
import { togglePinMessage } from "../../store/actions";
import { useStore } from "../../store/store";
import { previewText } from "../../utils/messages";
import { MenuButton } from "../common/ui";

/**
 * WhatsApp-style pinned-message bar above the conversation.
 *
 * Shows one pin at a time with a segment per pin on the left. Clicking the
 * bar jumps to that message and moves on to the next pin, so repeated clicks
 * walk through every pinned message. The chevron offers Unpin / Go to message.
 */
export default function PinnedBar({ room, me, canPin }) {
  const roomId = room.id;
  const [state, setState] = useState({ roomId: null, pins: [] });
  const [cursor, setCursor] = useState(0);
  const [refresh, setRefresh] = useState(0);
  // Re-read the pins when any loaded message of this chat is pinned/unpinned.
  const signature = useStore((store) =>
    (store.messages[roomId]?.items || [])
      .filter((item) => item.is_pinned)
      .map((item) => item.id)
      .join(","),
  );

  useEffect(() => {
    const onChange = (event) => {
      if (Number(event.detail?.roomId) === Number(roomId)) setRefresh((value) => value + 1);
    };
    window.addEventListener("whatsup:pins-changed", onChange);
    return () => window.removeEventListener("whatsup:pins-changed", onChange);
  }, [roomId]);

  useEffect(() => {
    let cancelled = false;
    chatApi
      .pinned(roomId)
      .then((pins) => !cancelled && setState({ roomId, pins }))
      .catch(() => !cancelled && setState({ roomId, pins: [] }));
    return () => {
      cancelled = true;
    };
  }, [roomId, signature, refresh]);

  const pins = useMemo(() => (state.roomId === roomId ? state.pins : []), [state, roomId]);
  const index = pins.length ? cursor % pins.length : 0;
  const current = pins[index];

  const goTo = useCallback((message) => {
    window.dispatchEvent(new CustomEvent("whatsup:jump-to", { detail: message.id }));
  }, []);

  if (!current) return null;

  const text = previewText(current, me.id) || "Message";
  const menu = [
    canPin ? { label: "Unpin", icon: PinOff, onClick: () => togglePinMessage(roomId, current) } : null,
    { label: "Go to message", icon: ArrowRight, onClick: () => goTo(current) },
  ].filter(Boolean);

  return (
    <div className="pinned-bar">
      <button
        type="button"
        className="pinned-bar__main"
        onClick={() => {
          goTo(current);
          setCursor((value) => value + 1);
        }}
        title={pins.length > 1 ? `Pinned message ${index + 1} of ${pins.length} · click for the next one` : "Go to pinned message"}
      >
        {pins.length > 1 ? (
          <span className="pinned-bar__segments" aria-hidden="true">
            {pins.map((pin, i) => (
              <span key={pin.id} className={i === index ? "is-active" : ""} />
            ))}
          </span>
        ) : null}
        <Pin size={18} className="pinned-bar__icon" />
        <span className="pinned-bar__text">{text}</span>
      </button>
      <MenuButton icon={ChevronDown} label="Pinned message options" items={menu} />
    </div>
  );
}
