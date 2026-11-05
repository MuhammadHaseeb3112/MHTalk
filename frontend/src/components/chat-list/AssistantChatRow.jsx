import { BadgeCheck, Sparkles } from "lucide-react";
import { listTime } from "../../utils/format";
import { useAssistant } from "../assistant/assistantStore";

/** "MHTalk AI" in the chat list, like the AI chat in WhatsApp's list. */
export default function AssistantChatRow({ active, onOpen }) {
  const { messages, sending } = useAssistant();
  const last = messages[messages.length - 1];
  let preview = "Ask me anything";
  if (sending) preview = "typing…";
  else if (last) preview = last.role === "user" ? `You: ${last.content}` : last.content;

  return (
    <div
      className={`chat-item chat-item--ai ${active ? "is-active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter") onOpen();
      }}
    >
      <span className="avatar-wrap">
        <span className="assistant-avatar assistant-avatar--list" aria-hidden>
          <Sparkles size={24} />
        </span>
      </span>
      <div className="chat-item__body">
        <div className="chat-item__top">
          <span className="chat-item__title">
            MHTalk AI <BadgeCheck size={15} className="chat-item__verified" aria-label="Official" />
          </span>
          <span className="chat-item__time">{last ? listTime(last.at) : ""}</span>
        </div>
        <div className="chat-item__bottom">
          <span className="chat-item__preview">
            <span className={sending ? "chat-item__typing" : "chat-item__text"}>{preview}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
