import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { BarChart3, Camera, FileText, Headphones, Image as ImageIcon, MapPin, Mic, ClipboardPaste, Paperclip, Pencil, Send, Smile, UserRound, X } from "lucide-react";
import { chatApi } from "../../api/endpoints";
import { realtime } from "../../services/realtime";
import { getNotificationPrefs } from "../../services/notify";
import { toast } from "../../services/toast";
import { editMessage, sendGif, sendLocation, sendPoll, sendSticker, sendText, sendVoice } from "../../store/actions";
import { useStore } from "../../store/store";
import { previewText, attachmentKind, profileName, URL_PATTERN } from "../../utils/messages";
import { openFilePicker } from "../../utils/files";
import { formatPhone, phoneDigits } from "../../utils/phone";
import { Avatar, Menu } from "../common/ui";
import { useMediaQuery } from "../../hooks";
import AttachSheet from "./AttachSheet";
import { readClipboardFiles } from "../../utils/clipboard";
import { startLiveLocation } from "../../services/liveLocation";
import { LinkPreviewCard } from "../messages/FeatureCards";
import EmojiPicker from "./EmojiPicker";
import { LocationDialog, PollComposerDialog } from "./FeatureDialogs";
import VoiceRecorder from "./VoiceRecorder";
import ShareContactDialog from "./ShareContactDialog";

const FIRST_URL = new RegExp(URL_PATTERN.source, "i");

/** The "@query" being typed right before the caret, if any. */
function mentionAt(value, caret) {
  const before = value.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at < 0 || (at > 0 && !/\s/.test(before[at - 1]))) return null;
  const query = before.slice(at + 1);
  if (/[\n@]/.test(query) || query.length > 40) return null;
  return { start: at, end: caret, query };
}

const drafts = new Map(); // per-room unsent text (kept for the session)
const MAX_FILES = 30;

/**
 * Message composer: auto-growing input, emoji picker, attachment menu,
 * voice recorder, reply/edit bars and debounced typing notifications.
 */
export default function Composer({ room, replyTo, editing, onClearReply, onClearEdit, onPickFiles, onOpenCamera, nameOf, blocked, disabledReason }) {
  const [text, setText] = useState(() => drafts.get(room.id) || "");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [attachAnchor, setAttachAnchor] = useState(null);
  const [attachSheet, setAttachSheet] = useState(false);
  const isMobile = useMediaQuery("(max-width: 700px)");
  const [recording, setRecording] = useState(false); // false | "tap" | "hold"
  const [gesture, setGesture] = useState({ dx: 0, dy: 0, locked: false });
  const recorderControl = useRef(null);
  const holdCleanup = useRef(null);
  const [shareContact, setShareContact] = useState(false);
  const [pollOpen, setPollOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [mention, setMention] = useState(null); // { start, end, query }
  const [mentionIndex, setMentionIndex] = useState(0);
  const pickedRef = useRef([]); // [{ id, label, phone }] chosen from the picker
  const pendingCaretRef = useRef(null);
  const [linkState, setLinkState] = useState({ url: "", preview: null });
  const [dismissedUrl, setDismissedUrl] = useState("");
  const inputRef = useRef(null);
  const emojiBtnRef = useRef(null);
  const typingRef = useRef({ active: false, timer: null });
  const inputId = useId();
  const fileIds = { media: `${inputId}-media`, doc: `${inputId}-doc`, audio: `${inputId}-audio` };
  const me = useStore((state) => state.me);

  // ---- @mentions (groups only) ------------------------------------------
  const canMention = Boolean(room.isGroup);
  const candidates = useMemo(() => {
    if (!canMention || !mention) return [];
    const term = mention.query.trim().toLowerCase();
    const digits = phoneDigits(term);
    return (room.participants || [])
      .map((participant) => participant.user)
      .filter((user) => user && Number(user.id) !== Number(me.id))
      .map((user) => {
        // Saved contact name; otherwise WhatsApp shows the number with "~ profile name".
        const saved = nameOf(user.id);
        const alias = profileName(user);
        const unsaved = !/[a-z]/i.test(saved);
        return { user, label: unsaved && alias ? alias : saved, alias: unsaved ? alias : "", phone: user.phone_number };
      })
      .filter(({ phone, label, alias }) =>
        !term ||
        label.toLowerCase().includes(term) ||
        alias.toLowerCase().includes(term) ||
        (digits.length >= 2 && phoneDigits(phone).includes(digits)))
      .sort((a, b) => a.label.localeCompare(b.label))
      .slice(0, 50);
  }, [canMention, mention, room.participants, me.id, nameOf]);
  const pickerOpen = candidates.length > 0 && !editing;

  function pickMention(candidate) {
    const node = inputRef.current;
    if (!mention || !candidate) return;
    const insert = `@${candidate.label} `;
    const next = text.slice(0, mention.start) + insert + text.slice(mention.end);
    pickedRef.current = [...pickedRef.current.filter((item) => item.id !== candidate.user.id), { id: candidate.user.id, label: candidate.label, phone: candidate.user.phone_number }];
    // Place the caret right after the inserted name in the same commit as
    // the new text (see the layout effect below), so fast typing continues there.
    pendingCaretRef.current = mention.start + insert.length;
    setText(next);
    setMention(null);
    node?.focus();
  }

  /** Swap "@Name" for the stored "@<phone>" token and collect the ids. */
  function resolveMentions(value) {
    let content = value;
    const ids = [];
    [...pickedRef.current, ...(editing ? editMentions : [])]
      .sort((a, b) => b.label.length - a.label.length)
      .forEach((item) => {
        const visible = `@${item.label}`;
        if (item.phone && content.includes(visible)) {
          content = content.split(visible).join(`@${item.phone}`);
          ids.push(item.id);
        }
      });
    return { content, ids };
  }

  // ---- link preview while typing ----------------------------------------
  const typedUrl = editing ? "" : (FIRST_URL.exec(text)?.[0] || "");
  useEffect(() => {
    if (!typedUrl || typedUrl === dismissedUrl) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      chatApi
        .linkPreview(typedUrl, { signal: controller.signal })
        .then((preview) => setLinkState({ url: typedUrl, preview: preview || null }))
        .catch(() => {});
    }, 500);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [typedUrl, dismissedUrl]);
  const shownPreview = typedUrl && typedUrl !== dismissedUrl && linkState.url === typedUrl ? linkState.preview : null;

  // Edit mode loads the message text (derived-state pattern, no effect needed).
  const [editingId, setEditingId] = useState(null);
  const [editMentions, setEditMentions] = useState([]); // mentions of the message being edited
  if ((editing?.id ?? null) !== editingId) {
    setEditingId(editing?.id ?? null);
    if (editing) {
      // Show "@Name" instead of the stored "@<phone>" tokens while editing.
      let value = editing.content || "";
      const found = [];
      (editing.mentions || []).forEach((id) => {
        const user = (room.participants || []).find((p) => Number(p.user?.id) === Number(id))?.user;
        if (!user?.phone_number) return;
        const label = nameOf(id);
        value = value.split(`@${user.phone_number}`).join(`@${label}`);
        found.push({ id: user.id, label, phone: user.phone_number });
      });
      setEditMentions(found);
      setText(value);
    }
  }
  useEffect(() => {
    if (!editing) return;
    const node = inputRef.current;
    node?.focus();
    const length = node?.value.length || 0;
    node?.setSelectionRange(length, length);
  }, [editing]);

  useEffect(() => {
    if (replyTo) inputRef.current?.focus();
  }, [replyTo]);

  useEffect(() => {
    if (!editing) drafts.set(room.id, text);
  }, [text, room.id, editing]);

  // Auto-grow up to ~6 lines.
  useLayoutEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    if (pendingCaretRef.current !== null) {
      node.setSelectionRange(pendingCaretRef.current, pendingCaretRef.current);
      pendingCaretRef.current = null;
    }
    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, 140)}px`;
  }, [text]);

  const stopTyping = useCallback(() => {
    window.clearTimeout(typingRef.current.timer);
    if (typingRef.current.active) {
      typingRef.current.active = false;
      realtime.sendTyping(false);
    }
  }, []);

  useEffect(() => stopTyping, [stopTyping]);

  function onChange(event) {
    setText(event.target.value);
    if (editing) return;
    if (canMention) {
      const found = mentionAt(event.target.value, event.target.selectionStart ?? event.target.value.length);
      setMention(found);
      if ((found?.query || "") !== (mention?.query || "")) setMentionIndex(0);
    }
    if (!typingRef.current.active && event.target.value.trim()) {
      typingRef.current.active = true;
      realtime.sendTyping(true);
    }
    window.clearTimeout(typingRef.current.timer);
    typingRef.current.timer = window.setTimeout(stopTyping, 2500);
  }

  async function submit() {
    const value = text.trim();
    if (!value) return;
    if (editing) {
      const edited = resolveMentions(value).content;
      if (edited !== editing.content) await editMessage(room.id, editing, edited);
      onClearEdit();
      setText(drafts.get(room.id) || "");
      return;
    }
    stopTyping();
    const { content, ids } = resolveMentions(value);
    const url = FIRST_URL.exec(value)?.[0] || "";
    const linkPreview = !url ? undefined : url === dismissedUrl ? false : linkState.url === url ? linkState.preview || undefined : undefined;
    setText("");
    setMention(null);
    pickedRef.current = [];
    setDismissedUrl("");
    drafts.delete(room.id);
    onClearReply?.();
    sendText(room.id, content, replyTo, { mentions: ids, linkPreview });
    inputRef.current?.focus();
  }

  function onKeyDown(event) {
    if (pickerOpen) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setMentionIndex((index) => (index + step + candidates.length) % candidates.length);
        return;
      }
      if ((event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
        event.preventDefault();
        pickMention(candidates[Math.min(mentionIndex, candidates.length - 1)]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setMention(null);
        return;
      }
    }
    const enterSends = getNotificationPrefs().enterToSend;
    if (event.key === "Enter" && !event.shiftKey && (enterSends || event.ctrlKey) && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
    if (event.key === "Escape") {
      if (editing) onClearEdit();
      else if (replyTo) onClearReply();
    }
    if (event.key === "ArrowUp" && !text) {
      window.dispatchEvent(new CustomEvent("mhtalk:edit-last"));
    }
  }

  function onPaste(event) {
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) {
      event.preventDefault();
      onPickFiles(files.slice(0, MAX_FILES), "media");
    }
  }

  function insertEmoji(emoji) {
    const node = inputRef.current;
    const start = node?.selectionStart ?? text.length;
    const end = node?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + emoji + text.slice(end);
    setText(next);
    window.requestAnimationFrame(() => {
      node?.focus();
      node?.setSelectionRange(start + emoji.length, start + emoji.length);
    });
  }

  function handleFiles(kind) {
    return (event) => {
      const files = [...(event.target.files || [])];
      event.target.value = "";
      if (!files.length) return;
      if (files.length > MAX_FILES) toast.error(`You can send up to ${MAX_FILES} files at once.`);
      onPickFiles(files.slice(0, MAX_FILES), kind);
    };
  }

  // WhatsApp-style mic: tap opens the recorder; press and hold records,
  // release sends, slide left cancels, slide up locks (hands-free).
  function onMicPointerDown(event) {
    if (editing || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.preventDefault();
    const hold = { id: event.pointerId, x: event.clientX, y: event.clientY, active: false };
    const finish = () => {
      window.clearTimeout(hold.timer);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      holdCleanup.current = null;
    };
    function onMove(moveEvent) {
      if (moveEvent.pointerId !== hold.id || !hold.active) return;
      const dx = Math.min(0, moveEvent.clientX - hold.x);
      const dy = Math.min(0, moveEvent.clientY - hold.y);
      if (dy < -80) {
        finish();
        setGesture({ dx: 0, dy: 0, locked: true });
        return;
      }
      if (dx < -120) {
        finish();
        recorderControl.current?.cancel();
        return;
      }
      setGesture({ dx, dy, locked: false });
    }
    function onUp(upEvent) {
      if (upEvent.pointerId !== hold.id) return;
      finish();
      if (hold.active) recorderControl.current?.release();
      else setRecording("tap");
    }
    function onCancel(cancelEvent) {
      if (cancelEvent.pointerId !== hold.id) return;
      finish();
      if (hold.active) recorderControl.current?.cancel();
    }
    hold.timer = window.setTimeout(() => {
      hold.active = true;
      setGesture({ dx: 0, dy: 0, locked: false });
      setRecording("hold");
    }, 250);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    holdCleanup.current = finish;
  }

  useEffect(() => () => holdCleanup.current?.(), []);

  async function sendVoiceNote(blob, seconds, waveform, viewOnce) {
    setRecording(false);
    await sendVoice(room.id, blob, seconds, waveform, viewOnce);
  }

  if (blocked || disabledReason) {
    return <div className="composer composer--disabled">{disabledReason || "You blocked this contact. Unblock to send a message."}</div>;
  }

  async function pasteFromClipboard() {
    const result = await readClipboardFiles();
    if (result.files.length) onPickFiles(result.files.slice(0, MAX_FILES), "media");
    else if (result.text) insertEmoji(result.text);
    else toast(result.error || "Clipboard is empty. Long-press the message box and choose Paste for text.");
  }

  const attachItems = [
    { label: "Gallery", icon: ImageIcon, tone: "gallery", onClick: () => openFilePicker(fileIds.media) },
    { label: "Camera", icon: Camera, tone: "camera", onClick: () => onOpenCamera?.() },
    { label: "Location", icon: MapPin, tone: "location", onClick: () => setLocationOpen(true) },
    { label: "Contact", icon: UserRound, tone: "contact", onClick: () => setShareContact(true) },
    { label: "Document", icon: FileText, tone: "document", onClick: () => openFilePicker(fileIds.doc) },
    { label: "Poll", icon: BarChart3, tone: "poll", onClick: () => setPollOpen(true) },
    { label: "Audio", icon: Headphones, tone: "audio", onClick: () => openFilePicker(fileIds.audio) },
    { label: "Paste", icon: ClipboardPaste, tone: "paste", onClick: pasteFromClipboard },
  ];

  const bar = editing ? (
    <div className="composer__bar composer__bar--edit">
      <Pencil size={18} />
      <div className="composer__bar-body">
        <span className="composer__bar-title">Edit message</span>
        <span className="composer__bar-text">{editing.content}</span>
      </div>
      <button type="button" className="icon-btn" onClick={() => { onClearEdit(); setText(drafts.get(room.id) || ""); }} aria-label="Cancel edit">
        <X size={20} />
      </button>
    </div>
  ) : replyTo ? (
    <div className="composer__bar">
      <div className="quote quote--composer" style={{ "--quote-color": Number(replyTo.sender?.id) === Number(me.id) ? "var(--accent)" : "var(--sender-2)" }}>
        <span className="quote__body">
          <span className="quote__name">{nameOf(replyTo.sender?.id)}</span>
          <span className="quote__text">{previewText(replyTo, me.id)}</span>
        </span>
        {replyTo.attachments?.[0] && attachmentKind(replyTo.attachments[0]) === "image" ? <img className="quote__thumb" src={replyTo.attachments[0].file} alt="" /> : null}
      </div>
      <button type="button" className="icon-btn" onClick={onClearReply} aria-label="Cancel reply">
        <X size={20} />
      </button>
    </div>
  ) : null;

  const mentionPicker = pickerOpen ? (
    <div className="mention-picker" role="listbox" aria-label="Mention a group member">
      {candidates.map((candidate, index) => (
        <button
          key={candidate.user.id}
          type="button"
          role="option"
          aria-selected={index === mentionIndex}
          className={`mention-picker__item ${index === mentionIndex ? "is-active" : ""}`}
          onMouseDown={(event) => event.preventDefault()}
          onMouseEnter={() => setMentionIndex(index)}
          onClick={() => pickMention(candidate)}
        >
          <Avatar src={candidate.user.profile?.profile_picture} name={candidate.label} size={32} />
          <span className="mention-picker__body">
            <span className="mention-picker__name">{candidate.alias ? formatPhone(candidate.phone) : candidate.label}</span>
            <span className="mention-picker__phone">{candidate.alias ? `~ ${candidate.alias}` : formatPhone(candidate.phone)}</span>
          </span>
        </button>
      ))}
    </div>
  ) : null;

  return (
    <footer className="composer">
      {mentionPicker}
      {bar}
      {shownPreview && !recording ? (
        <div className="composer__bar composer__bar--link">
          <LinkPreviewCard
            preview={shownPreview}
            compact
            onRemove={() => {
              setDismissedUrl(typedUrl);
              inputRef.current?.focus();
            }}
          />
        </div>
      ) : null}
      {emojiOpen ? <EmojiPicker
          className="emoji-picker--composer"
          onPick={insertEmoji}
          onGif={(gif) => {
            sendGif(room.id, gif, replyTo);
            if (replyTo) onClearReply();
            setEmojiOpen(false);
          }}
          onSticker={(file) => {
            sendSticker(room.id, file, replyTo);
            if (replyTo) onClearReply();
            setEmojiOpen(false);
          }}
          onClose={() => setEmojiOpen(false)}
          ignoreRefs={[emojiBtnRef]}
        /> : null}
      {recording ? (
        <VoiceRecorder
          hold={recording === "hold" && !gesture.locked}
          gesture={gesture}
          ref={recorderControl}
          onCancel={() => setRecording(false)}
          onSend={sendVoiceNote}
        />
      ) : (
        <div className="composer__row">
          <div className="composer__pill">
            <button
              ref={emojiBtnRef}
              type="button"
              className={`icon-btn ${emojiOpen ? "is-active" : ""}`}
              aria-label="Emoji, GIFs and stickers"
              onClick={() => setEmojiOpen((value) => !value)}
            >
              <Smile size={23} />
            </button>
            <textarea
              ref={inputRef}
              className="composer__input"
              rows={1}
              value={text}
              placeholder="Message"
              aria-label="Type a message"
              onChange={onChange}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              onBlur={() => {
                stopTyping();
                setMention(null);
              }}
              maxLength={65000}
            />
            <button
              type="button"
              className={`icon-btn ${attachAnchor || attachSheet ? "is-active" : ""}`}
              aria-label="Attach"
              onClick={(event) => {
                if (isMobile) setAttachSheet(true);
                else setAttachAnchor(attachAnchor ? null : event.currentTarget);
              }}
              disabled={Boolean(editing)}
            >
              <Paperclip size={22} className="composer__clip" />
            </button>
            {!text.trim() && onOpenCamera ? (
              <button type="button" className="icon-btn" aria-label="Camera" onClick={onOpenCamera} disabled={Boolean(editing)}>
                <Camera size={22} />
              </button>
            ) : null}
          </div>
          {text.trim() ? (
            <button type="button" className="send-btn composer__action" onClick={submit} aria-label={editing ? "Save edit" : "Send"}>
              <Send size={22} />
            </button>
          ) : (
            <button
              type="button"
              className="send-btn composer__action composer__mic"
              onPointerDown={onMicPointerDown}
              onClick={(event) => {
                // Keyboard (Enter/Space) only: pointer taps are handled on pointerup.
                if (event.detail === 0) setRecording("tap");
              }}
              onContextMenu={(event) => event.preventDefault()}
              aria-label="Record voice message"
              data-tooltip="Click to record, or hold to talk"
              disabled={Boolean(editing)}
            >
              <Mic size={23} />
            </button>
          )}
        </div>
      )}
      {attachAnchor ? <Menu anchor={attachAnchor} items={attachItems} align="right" onClose={() => setAttachAnchor(null)} /> : null}
      {attachSheet ? <AttachSheet items={attachItems} onClose={() => setAttachSheet(false)} /> : null}
      <input id={fileIds.media} type="file" accept="image/*,video/*" multiple hidden onChange={handleFiles("media")} />
      <input id={fileIds.doc} type="file" multiple hidden onChange={handleFiles("document")} />
      <input id={fileIds.audio} type="file" accept="audio/*" multiple hidden onChange={handleFiles("audio")} />
      {shareContact ? <ShareContactDialog room={room} onClose={() => setShareContact(false)} /> : null}
      {pollOpen ? (
        <PollComposerDialog
          onClose={() => setPollOpen(false)}
          onSend={(poll) => {
            setPollOpen(false);
            sendPoll(room.id, poll);
          }}
        />
      ) : null}
      {locationOpen ? (
        <LocationDialog
          onClose={() => setLocationOpen(false)}
          onSend={(location) => {
            setLocationOpen(false);
            sendLocation(room.id, location).then((saved) => {
              if (location.live_seconds && saved?.id) startLiveLocation(room.id, saved);
            });
          }}
        />
      ) : null}
    </footer>
  );
}

