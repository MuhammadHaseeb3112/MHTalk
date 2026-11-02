import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus } from "lucide-react";
import { useDismiss } from "../../hooks";
import { QUICK_REACTIONS } from "../../utils/emoji";
import EmojiPicker from "./EmojiPicker";

/** Quick reaction bar (👍 ❤️ 😂 😮 😢 🙏 +) anchored to a message. */
export default function ReactionPicker({ anchor, current, onPick, onClose }) {
  const ref = useRef(null);
  const [full, setFull] = useState(false);
  const [position, setPosition] = useState(null);
  useDismiss([ref], onClose, !full);

  useLayoutEffect(() => {
    const rect = anchor?.getBoundingClientRect ? anchor.getBoundingClientRect() : anchor;
    const node = ref.current;
    if (!rect || !node) return;
    const width = node.offsetWidth;
    const height = node.offsetHeight;
    let left = rect.left + rect.width / 2 - width / 2;
    left = Math.max(8, Math.min(window.innerWidth - width - 8, left));
    let top = rect.top - height - 8;
    if (top < 8) top = rect.bottom + 8;
    top = Math.min(top, window.innerHeight - height - 8);
    setPosition({ left, top });
  }, [anchor, full]);

  return createPortal(
    <div ref={ref} className={`reaction-picker ${full ? "is-full" : ""}`} style={position || { visibility: "hidden", left: 0, top: 0 }}>
      {full ? (
        <EmojiPicker
          onPick={(emoji) => {
            onPick(emoji);
            onClose();
          }}
          onClose={onClose}
        />
      ) : (
        <div className="reaction-picker__bar">
          {QUICK_REACTIONS.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className={`emoji ${current === emoji ? "is-current" : ""}`}
              onClick={() => {
                onPick(emoji);
                onClose();
              }}
              aria-label={`React ${emoji}`}
            >
              {emoji}
            </button>
          ))}
          <button type="button" className="reaction-picker__more" onClick={() => setFull(true)} aria-label="More reactions">
            <Plus size={20} />
          </button>
        </div>
      )}
    </div>,
    document.body,
  );
}
