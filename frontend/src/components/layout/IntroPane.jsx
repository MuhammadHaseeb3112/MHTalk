import { FileText, MessageSquarePlus, Phone, UserPlus } from "lucide-react";
import { LogoMark } from "../common/Icons";

/** Right-hand placeholder shown when no conversation is open. */
export default function IntroPane({ onNewChat, onNewContact, onCalls }) {
  return (
    <section className="intro">
      <div className="intro__card">
        <LogoMark size={72} />
        <h2>MHTalk Web</h2>
        <p>Send and receive messages, photos, videos and voice notes. Everything stays in sync across your open tabs.</p>
      </div>
      <div className="intro__actions">
        <button type="button" onClick={onNewChat}>
          <span><MessageSquarePlus size={22} /></span>
          New chat
        </button>
        <button type="button" onClick={onNewContact}>
          <span><UserPlus size={22} /></span>
          Add contact
        </button>
        <button type="button" onClick={onCalls}>
          <span><Phone size={22} /></span>
          Calls
        </button>
        <button type="button" onClick={onNewChat}>
          <span><FileText size={22} /></span>
          Send document
        </button>
      </div>
    </section>
  );
}
