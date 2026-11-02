import { useState } from "react";
import { Phone, Video } from "lucide-react";
import NewCallDialog from "./NewCallDialog";

/** Right-hand pane of the Calls section. */
export default function CallsMain() {
  const [open, setOpen] = useState(false);
  return (
    <section className="intro intro--calls">
      <div className="intro__card">
        <div className="calls-art" aria-hidden>
          <Video size={34} />
          <Phone size={30} />
        </div>
        <h2>Voice and video calling</h2>
        <p>Call your contacts or your groups (up to 8 people) with audio or video, right from your browser.</p>
      </div>
      <div className="intro__actions">
        <button type="button" onClick={() => setOpen(true)}>
          <span className="is-accent"><Video size={22} /></span>
          Start call
        </button>
        <button type="button" onClick={() => setOpen(true)}>
          <span><Phone size={22} /></span>
          Call a number
        </button>
      </div>
      {open ? <NewCallDialog onClose={() => setOpen(false)} /> : null}
    </section>
  );
}
