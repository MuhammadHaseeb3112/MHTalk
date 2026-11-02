import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Crop, Lock, Palette, Send, Smile, Type, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { statusApi } from "../../api/endpoints";
import { useObjectUrl } from "../../hooks";
import { loadStatus } from "../../store/actions";
import { useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { IconButton, Modal, Spinner } from "../common/ui";
import EmojiPicker from "../conversation/EmojiPicker";
import ImageEditor from "../media/ImageEditor";
import { getStatusPrivacy, setStatusPrivacy, STATUS_COLORS } from "./statusPrefs";
import StatusPrivacyEditor from "./StatusPrivacyEditor";

const FONTS = ["inherit", "Georgia, serif", "'Courier New', monospace", "'Trebuchet MS', sans-serif"];
const LABELS = { CONTACTS: "My contacts", CONTACTS_EXCEPT: "My contacts except…", ONLY_SHARE_WITH: "Only share with…", EVERYONE: "Everyone" };

/** Create a text, photo or video status (24h). */
export default function StatusComposer({ initialFile, mode = "text", onClose }) {
  const me = useStore((state) => state.me);
  const [file, setFile] = useState(initialFile || null);
  const [editing, setEditing] = useState(false);
  const [captionEmoji, setCaptionEmoji] = useState(false);
  const captionEmojiRef = useRef(null);
  const [text, setText] = useState("");
  const [caption, setCaption] = useState("");
  const [color, setColor] = useState(STATUS_COLORS[0]);
  const [font, setFont] = useState(0);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const emojiRef = useRef(null);
  const url = useObjectUrl(file);
  const [privacy, setPrivacy] = useState(() => getStatusPrivacy(me.id));
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const isText = mode === "text" && !file;
  const isVideo = file?.type.startsWith("video/");

  async function publish() {
    if (isText && !text.trim()) {
      toast.error("Type a status first.");
      return;
    }
    if (privacy.visibility === "ONLY_SHARE_WITH" && !privacy.users.length) {
      toast.error("Status privacy is set to “Only share with…” but no contacts are selected.");
      return;
    }
    setBusy(true);
    try {
      await statusApi.upload(
        {
          status_type: isText ? "TEXT" : isVideo ? "VIDEO" : "IMAGE",
          content: isText ? text.trim() : caption.trim(),
          media: isText ? undefined : file,
          background_color: color,
          text_color: "#FFFFFF",
          visibility: privacy.visibility,
          users: ["CONTACTS_EXCEPT", "ONLY_SHARE_WITH"].includes(privacy.visibility) ? privacy.users : undefined,
        },
        (event) => event.total && setProgress(Math.round((event.loaded / event.total) * 100)),
      );
      await loadStatus();
      toast.success("Status posted");
      onClose();
    } catch (error) {
      toast.error(errorMessage(error, "Couldn't post the status."));
      setBusy(false);
    }
  }

  if (editing && file && !isVideo) {
    return createPortal(
      <div className="status-composer status-composer--editing" role="dialog" aria-label="Edit photo">
        <ImageEditor
          file={file}
          url={url}
          onCancel={() => setEditing(false)}
          onApply={(edited) => {
            setFile(edited);
            setEditing(false);
          }}
        />
      </div>,
      document.body,
    );
  }

  return createPortal(
    <div className={`status-composer ${isText ? "" : "status-composer--media"}`} style={isText ? { background: color } : undefined} role="dialog" aria-label="New status">
      <div className="status-composer__top">
        <IconButton icon={X} label="Close" onClick={onClose} />
        {isText ? (
          <div className="status-composer__tools">
            <span ref={emojiRef}><IconButton icon={Smile} label="Emoji" onClick={() => setEmojiOpen((value) => !value)} /></span>
            <IconButton icon={Type} label="Change font" onClick={() => setFont((value) => (value + 1) % FONTS.length)} />
            <IconButton icon={Palette} label="Change color" onClick={() => setColor(STATUS_COLORS[(STATUS_COLORS.indexOf(color) + 1) % STATUS_COLORS.length])} />
          </div>
        ) : file && !isVideo ? (
          <div className="status-composer__tools">
            <IconButton icon={Crop} label="Crop, rotate and draw" onClick={() => setEditing(true)} />
          </div>
        ) : null}
      </div>
      <div className="status-composer__stage">
        {isText ? (
          <textarea
            className="status-composer__text"
            style={{ fontFamily: FONTS[font] }}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Type a status"
            maxLength={700}
            autoFocus
          />
        ) : file ? (
          isVideo ? <video src={url} controls playsInline /> : <img src={url} alt="Status preview" />
        ) : null}
        {emojiOpen ? <EmojiPicker className="emoji-picker--status" ignoreRefs={[emojiRef]} onClose={() => setEmojiOpen(false)} onPick={(emoji) => setText((value) => value + emoji)} /> : null}
      </div>
      <div className="status-composer__bottom">
        {!isText ? (
          <div className="status-composer__caption">
            <span ref={captionEmojiRef}>
              <IconButton icon={Smile} label="Emoji" onClick={() => setCaptionEmoji((value) => !value)} />
            </span>
            <input
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && !busy && publish()}
              placeholder="Add a caption"
              maxLength={700}
              autoFocus
            />
            {captionEmoji ? (
              <EmojiPicker
                className="emoji-picker--caption"
                ignoreRefs={[captionEmojiRef]}
                onClose={() => setCaptionEmoji(false)}
                onPick={(emoji) => setCaption((value) => value + emoji)}
              />
            ) : null}
          </div>
        ) : (
          <span className="status-composer__count">{700 - text.length}</span>
        )}
        <button type="button" className="status-composer__privacy" onClick={() => setPrivacyOpen(true)} title="Choose who can see this status">
          <Lock size={13} /> {LABELS[privacy.visibility]}
        </button>
        <button type="button" className="fab" onClick={publish} disabled={busy} aria-label="Post status">
          {busy ? <span className="fab__progress">{progress ? `${progress}%` : <Spinner size={18} className="spinner--dark" />}</span> : <Send size={22} />}
        </button>
      </div>
      {privacyOpen ? (
        <Modal
          title="Status privacy"
          className="status-privacy-modal"
          onClose={() => setPrivacyOpen(false)}
          footer={<button type="button" className="btn btn--primary" onClick={() => setPrivacyOpen(false)}>Done</button>}
        >
          <StatusPrivacyEditor
            value={privacy}
            onChange={(next) => {
              // Like WhatsApp: the choice also becomes the default for next time.
              setPrivacy(next);
              setStatusPrivacy(me.id, next);
            }}
          />
        </Modal>
      ) : null}
    </div>,
    document.body,
  );
}
