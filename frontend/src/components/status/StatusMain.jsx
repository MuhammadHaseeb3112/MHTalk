import { Camera, Pencil } from "lucide-react";
import { StatusIcon } from "../common/Icons";

/** Right-hand pane of the Status section. */
export default function StatusMain() {
  const start = (mode) => window.dispatchEvent(new CustomEvent("mhtalk:new-status", { detail: mode }));
  return (
    <section className="intro intro--status">
      <div className="intro__card">
        <span className="status-art"><StatusIcon size={72} /></span>
        <h2>Share status updates</h2>
        <p>Share photos, videos and text that disappear after 24 hours.</p>
      </div>
      <div className="intro__actions">
        <button type="button" onClick={() => start("text")}>
          <span><Pencil size={22} /></span>
          Text status
        </button>
        <button type="button" onClick={() => start("media")}>
          <span><Camera size={22} /></span>
          Photo and video
        </button>
      </div>
    </section>
  );
}
