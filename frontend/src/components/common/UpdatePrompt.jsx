import { useState } from "react";
import { RefreshCw, Sparkles, X } from "lucide-react";
import { applyUpdate, hideUpdatePrompt, requestOpenUpdate, useAppUpdate } from "../../services/appUpdate";

/** "New version available — Update now / Later" card (disappears after 12 s). */
export default function UpdatePrompt() {
  const update = useAppUpdate();
  const [busy, setBusy] = useState(false);
  if (!update.prompt) return null;
  const title = update.latest?.title;
  return (
    <div className="update-prompt" role="status" aria-live="polite">
      <span className="update-prompt__icon"><Sparkles size={20} /></span>
      <div className="update-prompt__text">
        <strong>New version of MHTalk</strong>
        <span>{title ? `${title}. ` : ""}Update now or later from Settings.</span>
        <button
          type="button"
          className="update-prompt__link"
          onClick={() => {
            hideUpdatePrompt();
            requestOpenUpdate();
          }}
        >
          What's new
        </button>
      </div>
      <div className="update-prompt__actions">
        <button type="button" className="update-prompt__later" onClick={hideUpdatePrompt}>Later</button>
        <button
          type="button"
          className="update-prompt__now"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            applyUpdate();
          }}
        >
          <RefreshCw size={15} className={busy ? "spin" : ""} /> {busy ? "Updating…" : "Update"}
        </button>
      </div>
      <button type="button" className="update-prompt__close" aria-label="Close" onClick={hideUpdatePrompt}>
        <X size={16} />
      </button>
    </div>
  );
}
