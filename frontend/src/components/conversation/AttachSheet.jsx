import { createPortal } from "react-dom";

/** WhatsApp-style bottom sheet with a grid of round, coloured attach options. */
export default function AttachSheet({ items, onClose }) {
  return createPortal(
    <div className="attach-sheet__backdrop" onClick={onClose} role="presentation">
      <div className="attach-sheet" role="menu" aria-label="Attach" onClick={(event) => event.stopPropagation()}>
        <span className="attach-sheet__grip" aria-hidden="true" />
        <div className="attach-sheet__grid">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className="attach-sheet__item"
              onClick={() => {
                onClose();
                item.onClick();
              }}
            >
              <span className={`attach-sheet__icon attach-sheet__icon--${item.tone || "default"}`}>
                <item.icon size={24} />
              </span>
              <span className="attach-sheet__label">{item.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
