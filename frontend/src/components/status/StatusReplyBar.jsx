import { useRef, useState } from "react";
import { FileText, Headphones, Image as ImageIcon, MapPin, Mic, Paperclip, Send, Smile } from "lucide-react";
import { errorMessage } from "../../api/client";
import { statusApi } from "../../api/endpoints";
import { openChatWith, sendFile, sendGif, sendLocation, sendSticker, sendVoice } from "../../store/actions";
import { toast } from "../../services/toast";
import { emojiOnly, rememberEmoji } from "../../utils/emoji";
import { normalizeFiles } from "../../utils/files";
import { Menu } from "../common/ui";
import EmojiPicker from "../conversation/EmojiPicker";
import { LocationDialog } from "../conversation/FeatureDialogs";
import VoiceRecorder from "../conversation/VoiceRecorder";

const QUICK = ["😂", "❤️"];

/**
 * WhatsApp's status reply bar: type a reply, or send an emoji, sticker, GIF,
 * voice message, photo, video, document, audio or location. Every reply goes
 * to the private chat with a "Name · Status" card on top.
 */
export default function StatusReplyBar({ status, owner, onPause, onResume }) {
  const [text, setText] = useState("");
  const [panel, setPanel] = useState(false);
  const [recording, setRecording] = useState(false);
  const [attach, setAttach] = useState(null);
  const [locating, setLocating] = useState(false);
  const emojiBtnRef = useRef(null);
  const mediaRef = useRef(null);
  const docRef = useRef(null);
  const audioRef = useRef(null);

  const statusRef = {
    id: status.id,
    snapshot: {
      status_id: status.id,
      status_type: status.status_type,
      status_text: (status.content || "").slice(0, 180),
      status_media: status.media || "",
      status_bg: status.background_color || "",
      status_fg: status.text_color || "",
      owner_id: owner?.id,
    },
  };

  async function deliver(send, label = "Reply sent") {
    try {
      const roomId = await openChatWith(owner);
      await send(roomId, statusRef);
      toast.success(label);
    } catch (error) {
      toast.error(errorMessage(error));
    }
    onResume();
  }

  async function react(emoji) {
    rememberEmoji(emoji);
    try {
      await statusApi.react(status.id, emoji);
      toast.success(`Reacted ${emoji}`);
    } catch (error) {
      toast.error(errorMessage(error));
    }
    onResume();
  }

  async function submit(event) {
    event?.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText("");
    setPanel(false);
    // Only emoji (from the keyboard or the panel): a reaction, like WhatsApp.
    const emoji = emojiOnly(value);
    if (emoji) {
      await react(emoji);
      return;
    }
    try {
      await statusApi.reply(status.id, value);
      toast.success("Reply sent");
    } catch (error) {
      toast.error(errorMessage(error));
    }
    onResume();
  }

  function pickFiles(kind) {
    return async (event) => {
      const files = await normalizeFiles([...(event.target.files || [])]);
      event.target.value = "";
      if (!files.length) return;
      deliver(async (roomId, ref) => {
        for (const file of files.slice(0, 10)) await sendFile(roomId, file, { status: ref, messageType: kind === "document" ? "DOCUMENT" : null });
      });
    };
  }

  if (recording) {
    return (
      <div className="status-reply status-reply--recording">
        <VoiceRecorder
          onCancel={() => {
            setRecording(false);
            onResume();
          }}
          onSend={(blob, seconds, peaks, viewOnce) => {
            setRecording(false);
            deliver((roomId, ref) => sendVoice(roomId, blob, seconds, peaks, viewOnce, { status: ref }), "Voice reply sent");
          }}
        />
      </div>
    );
  }

  return (
    <div className="status-reply">
      {panel ? (
        <EmojiPicker
          className="emoji-picker--status"
          ignoreRefs={[emojiBtnRef]}
          onPick={(emoji) => setText((value) => value + emoji)}
          onGif={(gif) => {
            setPanel(false);
            deliver((roomId, ref) => sendGif(roomId, gif, null, { status: ref }), "GIF sent");
          }}
          onSticker={(file) => {
            setPanel(false);
            deliver((roomId, ref) => sendSticker(roomId, file, null, { status: ref }), "Sticker sent");
          }}
          onClose={() => setPanel(false)}
        />
      ) : null}
      <form className="status-viewer__reply" onSubmit={submit}>
        <div className="status-reply__pill">
          <button
            ref={emojiBtnRef}
            type="button"
            className="icon-btn status-viewer__emoji"
            aria-label="Emoji, stickers and GIFs"
            onClick={() => {
              onPause();
              setPanel((value) => !value);
            }}
          >
            <Smile size={24} />
          </button>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            onFocus={onPause}
            onBlur={() => !panel && !text && onResume()}
            placeholder="Reply…"
            maxLength={1000}
            aria-label="Reply to status"
          />
          {!text ? (
            <>
              {QUICK.map((emoji) => (
                <button key={emoji} type="button" className="status-reply__quick emoji" onClick={() => react(emoji)} aria-label={`React ${emoji}`}>
                  {emoji}
                </button>
              ))}
              <button
                type="button"
                className="icon-btn status-viewer__emoji"
                aria-label="Attach"
                onClick={(event) => {
                  onPause();
                  setAttach(event.currentTarget);
                }}
              >
                <Paperclip size={22} />
              </button>
            </>
          ) : null}
        </div>
        {text.trim() ? (
          <button type="submit" className="send-btn" aria-label="Send reply">
            <Send size={18} />
          </button>
        ) : (
          <button
            type="button"
            className="send-btn"
            aria-label="Record voice reply"
            onClick={() => {
              onPause();
              setRecording(true);
            }}
          >
            <Mic size={20} />
          </button>
        )}
      </form>
      {attach ? (
        <Menu
          anchor={attach}
          align="right"
          onClose={() => setAttach(null)}
          items={[
            { label: "Photos & videos", icon: ImageIcon, onClick: () => mediaRef.current?.click() },
            { label: "Document", icon: FileText, onClick: () => docRef.current?.click() },
            { label: "Audio", icon: Headphones, onClick: () => audioRef.current?.click() },
            { label: "Location", icon: MapPin, onClick: () => setLocating(true) },
          ]}
        />
      ) : null}
      <input ref={mediaRef} type="file" accept="image/*,video/*" multiple hidden onChange={pickFiles("media")} />
      <input ref={docRef} type="file" multiple hidden onChange={pickFiles("document")} />
      <input ref={audioRef} type="file" accept="audio/*" multiple hidden onChange={pickFiles("audio")} />
      {locating ? (
        <LocationDialog
          onClose={() => {
            setLocating(false);
            onResume();
          }}
          onSend={(location) => {
            setLocating(false);
            deliver((roomId, ref) => sendLocation(roomId, location, { status: ref }), "Location sent");
          }}
        />
      ) : null}
    </div>
  );
}
