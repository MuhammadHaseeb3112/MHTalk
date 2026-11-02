import { useEffect } from "react";
import { Eraser, MessageSquareText, Sparkles } from "lucide-react";
import { PanelHeader } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { askAssistant, clearAssistant, loadAssistantStatus, useAssistant } from "./assistantStore";

const SUGGESTIONS = [
  "Write a short birthday wish for my friend",
  "Mujhe ek professional leave application likh do",
  "Explain how to stay productive while working from home",
  "Give me 5 caption ideas for a travel photo",
];

/** Sidebar for MHTalk AI: what it is, quick prompts and clearing the chat. */
export default function AssistantPanel() {
  const { messages, status } = useAssistant();
  useEffect(() => {
    loadAssistantStatus();
  }, []);

  return (
    <section className="panel assistant-panel">
      <PanelHeader title="MHTalk AI" />
      <div className="panel__scroll">
        <div className="assistant-intro">
          <span className="assistant-avatar assistant-avatar--lg"><Sparkles size={30} /></span>
          <h3>Ask MHTalk AI anything</h3>
          <p>Get answers, ideas and drafts in a chat. Your AI chat stays on this device.</p>
          {status && !status.enabled ? (
            <div className="assistant-intro__warn">
              <strong>Turn it on for free:</strong>
              <ol>
                <li>
                  Get a free Google Gemini key at{" "}
                  <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">aistudio.google.com/apikey</a>
                </li>
                <li>
                  In the backend <code>.env</code> add <code>WHATSUP_AI_API_KEY=your-key</code>
                </li>
                <li>Restart the backend</li>
              </ol>
            </div>
          ) : null}
          {status?.enabled ? (
            <p className="assistant-intro__provider">Powered by {status.provider_label || status.provider}</p>
          ) : null}
        </div>
        <div className="section-label">Try asking</div>
        <div className="list-pad">
          {SUGGESTIONS.map((text) => (
            <button key={text} type="button" className="row assistant-suggestion" onClick={() => askAssistant(text)} disabled={status && !status.enabled}>
              <span className="doc__icon"><MessageSquareText size={18} /></span>
              <span className="row__body"><span className="row__title row__title--wrap">{text}</span></span>
            </button>
          ))}
          {messages.length ? (
            <button
              type="button"
              className="row assistant-suggestion danger-text"
              onClick={() =>
                confirmAction({
                  title: "Clear MHTalk AI chat?",
                  message: "This removes the AI conversation from this device.",
                  confirmLabel: "Clear chat",
                  danger: true,
                  onConfirm: clearAssistant,
                })
              }
            >
              <span className="doc__icon"><Eraser size={18} /></span>
              <span className="row__body"><span className="row__title">Clear AI chat</span></span>
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
