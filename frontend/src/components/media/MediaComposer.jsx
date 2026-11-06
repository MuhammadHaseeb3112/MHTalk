import { useEffect, useRef, useState } from "react";
import { Copy, Crop, Download, FileText, Grid3x3, Headphones, Pencil, Plus, Redo2, Send, Smile, Square, Type, Undo2, X } from "lucide-react";
import { toast } from "../../services/toast";
import { normalizeFiles, validateFiles } from "../../utils/files";
import { fileSize } from "../../utils/format";
import { COLORS, composedBlob, preparePhoto } from "./markup";
import MarkupCanvas from "./MarkupCanvas";
import { attachmentKind } from "../../utils/messages";
import { IconButton } from "../common/ui";
import EmojiPicker from "../conversation/EmojiPicker";
import { ViewOnceIcon } from "../messages/FeatureCards";
import ImageEditor from "./ImageEditor";
import VideoTrimmer from "./VideoTrimmer";
import { useTrimLoop } from "./useTrimLoop";

const MAX_ITEMS = 30;

let nextId = 1;
// Revoke after the current render so <img> tags still showing the URL don't fail.
function revokeLater(url) {
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function toItem(file) {
  return {
    id: nextId++,
    file,
    url: URL.createObjectURL(file),
    caption: "",
    viewOnce: false,
    hd: false,
    ops: [], // photo markup (pencil, text, shapes, blur, emoji)
    redo: [],
    kind: attachmentKind({ mime_type: file.type, file_name: file.name }),
  };
}

/**
 * Full-pane preview before sending media/documents, laid out like WhatsApp
 * Web: a tool bar for photos (crop & rotate, pencil, text, rectangle, blur,
 * emoji, HD, undo / redo, copy, download), large preview, per-item caption,
 * thumbnail strip with "add more", and a send button with the item count.
 * Photos are sent in standard quality (resized) unless HD is on.
 */
export default function MediaComposer({ initialFiles, mode, title, onSend, onClose }) {
  const [items, setItems] = useState(() => initialFiles.map(toItem));
  const [active, setActive] = useState(0);
  const [editing, setEditing] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [tool, setTool] = useState(null); // draw | text | rect | blur | null
  const [color, setColor] = useState(COLORS[2]);
  const [stickerOpen, setStickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const stickerBtnRef = useRef(null);
  const addRef = useRef(null);
  const captionRef = useRef(null);
  const emojiBtnRef = useRef(null);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  // Free the object URLs when the composer closes. In development React
  // mounts twice (StrictMode), so the revoke is cancelled if we come back.
  const disposeRef = useRef(0);
  useEffect(() => {
    window.clearTimeout(disposeRef.current);
    return () => {
      disposeRef.current = window.setTimeout(() => itemsRef.current.forEach((item) => URL.revokeObjectURL(item.url)), 2000);
    };
  }, []);

  useEffect(() => {
    if (!items.length) onClose();
  }, [items.length, onClose]);

  const current = items[Math.min(active, items.length - 1)];
  const videoRef = useRef(null);
  useTrimLoop(videoRef, current?.kind === "video" ? current.trim : null);
  const accept = mode === "media" ? "image/*,video/*" : mode === "audio" ? "audio/*" : undefined;

  function remove(id) {
    const index = items.findIndex((item) => item.id === id);
    if (index < 0) return;
    revokeLater(items[index].url);
    const next = items.filter((item) => item.id !== id);
    setItems(next);
    setActive((value) => Math.max(0, Math.min(value >= index ? value - 1 : value, next.length - 1)));
  }

  async function addMore(event) {
    const picked = [...(event.target.files || [])];
    event.target.value = "";
    const files = validateFiles(await normalizeFiles(picked), mode);
    if (!files.length) return;
    const room = MAX_ITEMS - items.length;
    if (files.length > room) toast.error(`You can send up to ${MAX_ITEMS} items at once.`);
    const added = files.slice(0, Math.max(0, room)).map(toItem);
    setActive(items.length);
    setItems([...items, ...added]);
  }

  // WhatsApp's "1" button: the recipient can open this photo/video only once.
  function toggleViewOnce() {
    const next = !current.viewOnce;
    setItems((list) => list.map((item) => (item.id === current.id ? { ...item, viewOnce: next } : item)));
    toast(next ? `${current.kind === "video" ? "Video" : "Photo"} set to view once` : "View once turned off");
  }

  function setCaption(value) {
    setItems((list) => list.map((item) => (item.id === current.id ? { ...item, caption: value } : item)));
  }

  function patchCurrent(patch) {
    setItems((list) => list.map((item) => (item.id === current.id ? { ...item, ...patch } : item)));
  }

  function setOps(ops) {
    patchCurrent({ ops, redo: [] });
  }

  function undo() {
    if (!current.ops.length) return;
    patchCurrent({ ops: current.ops.slice(0, -1), redo: [...current.redo, current.ops[current.ops.length - 1]] });
  }

  function redo() {
    if (!current.redo.length) return;
    patchCurrent({ ops: [...current.ops, current.redo[current.redo.length - 1]], redo: current.redo.slice(0, -1) });
  }

  function pickTool(next) {
    setTool((value) => (value === next ? null : next));
  }

  async function openCrop() {
    setTool(null);
    if (current.ops.length) {
      // Crop works on pixels: bake the markup in first.
      try {
        const blob = await composedBlob(current, current.file.type === "image/png" ? "image/png" : "image/jpeg");
        const file = new File([blob], current.file.name, { type: blob.type });
        revokeLater(current.url);
        patchCurrent({ file, url: URL.createObjectURL(file), ops: [], redo: [] });
      } catch (error) {
        toast.error(error.message);
        return;
      }
    }
    setEditing(true);
  }

  function applyEdit(file) {
    revokeLater(current.url);
    const url = URL.createObjectURL(file);
    setItems((list) => list.map((item) => (item.id === current.id ? { ...item, file, url, edited: true, ops: [], redo: [] } : item)));
    setEditing(false);
  }

  async function copyImage() {
    try {
      const blob = await composedBlob(current);
      await navigator.clipboard.write([new window.ClipboardItem({ "image/png": blob })]);
      toast("Image copied");
    } catch {
      toast.error("Your browser doesn't allow copying images.");
    }
  }

  async function downloadImage() {
    const blob = await composedBlob(current);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = current.file.name.replace(/\.[^.]+$/, "") + ".png";
    link.click();
    revokeLater(link.href);
  }

  function toggleHd() {
    const next = !current.hd;
    patchCurrent({ hd: next });
    toast(next ? "HD: photo will be sent in full resolution" : "Standard quality: faster to send");
  }

  async function send() {
    if (busy) return;
    setBusy(true);
    try {
      const prepared = await Promise.all(
        items.map(async (item) => ({
          file: item.kind === "image" ? await preparePhoto(item) : item.file,
          caption: item.caption.trim(),
          viewOnce: item.viewOnce && (item.kind === "image" || item.kind === "video"),
          // Only send a trim when the user actually shortened the video.
          trim: item.kind === "video" && item.trim && item.duration && (item.trim.start > 0.05 || item.trim.end < item.duration - 0.05) ? item.trim : null,
        })),
      );
      onSend(prepared);
    } catch (error) {
      toast.error(error.message || "Couldn't prepare the photos.");
      setBusy(false);
    }
  }

  if (!current) return null;

  if (editing && current.kind === "image") {
    return (
      <div className="media-composer">
        <ImageEditor file={current.file} url={current.url} onCancel={() => setEditing(false)} onApply={applyEdit} />
      </div>
    );
  }

  const isPhoto = current.kind === "image" && current.file.type !== "image/gif";
  const tools = [
    { id: "draw", icon: Pencil, label: "Draw" },
    { id: "text", icon: Type, label: "Text" },
    { id: "rect", icon: Square, label: "Shape" },
    { id: "blur", icon: Grid3x3, label: "Blur" },
  ];

  return (
    <div className="media-composer" role="dialog" aria-label="Send media">
      <div className="media-composer__top">
        <IconButton icon={X} label="Discard" onClick={onClose} />
        {isPhoto ? (
          <>
            <div className="media-tools" role="toolbar" aria-label="Edit photo">
              <IconButton icon={Crop} label="Crop and rotate" onClick={openCrop} />
              {tools.map((item) => (
                <IconButton key={item.id} icon={item.icon} label={item.label} active={tool === item.id} onClick={() => pickTool(item.id)} />
              ))}
              <span ref={stickerBtnRef}>
                <IconButton icon={Smile} label="Emoji sticker" active={stickerOpen} onClick={() => setStickerOpen((value) => !value)} />
              </span>
              <button type="button" className={`media-tools__hd ${current.hd ? "is-on" : ""}`} aria-pressed={current.hd} onClick={toggleHd} title="HD quality">
                HD
              </button>
              <span className="media-tools__sep" />
              <IconButton icon={Undo2} label="Undo" disabled={!current.ops.length} onClick={undo} />
              <IconButton icon={Redo2} label="Redo" disabled={!current.redo.length} onClick={redo} />
              {stickerOpen ? (
                <EmojiPicker
                  className="emoji-picker--tools"
                  ignoreRefs={[stickerBtnRef]}
                  onClose={() => setStickerOpen(false)}
                  onPick={(emoji) => {
                    setOps([...current.ops, { type: "emoji", text: emoji, x: 0.5, y: 0.5, size: 0.16 }]);
                    setStickerOpen(false);
                    setTool(null);
                    toast("Drag the sticker to move it");
                  }}
                />
              ) : null}
            </div>
            <div className="media-composer__actions">
              <IconButton icon={Copy} label="Copy" onClick={copyImage} />
              <IconButton icon={Download} label="Download" onClick={downloadImage} />
            </div>
          </>
        ) : (
          <span className="media-composer__title">{title ? `Send to ${title}` : ""}</span>
        )}
      </div>
      {isPhoto && (tool === "draw" || tool === "text" || tool === "rect") ? (
        <div className="media-colors" role="radiogroup" aria-label="Colour">
          {COLORS.map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={color === value}
              aria-label={`Colour ${value}`}
              className={`media-colors__swatch ${color === value ? "is-active" : ""}`}
              style={{ background: value }}
              onClick={() => setColor(value)}
            />
          ))}
        </div>
      ) : null}

      {current?.kind === "video" && current.duration ? (
        <VideoTrimmer url={current.url} duration={current.duration} value={current.trim} onChange={(trim) => patchCurrent({ trim })} sizeBytes={current.file.size} />
      ) : null}
      <div className="media-composer__preview">
        {isPhoto ? (
          <MarkupCanvas key={current.id} url={current.url} alt={current.file.name} ops={current.ops} tool={tool} color={color} onChange={setOps} />
        ) : current.kind === "image" ? (
          <img src={current.url} alt={current.file.name} />
        ) : current.kind === "video" ? (
          <video
            key={current.url}
            ref={videoRef}
            src={current.url}
            controls
            playsInline
            onLoadedMetadata={(event) => {
              const total = event.currentTarget.duration;
              if (Number.isFinite(total) && !current.duration) patchCurrent({ duration: total, trim: { start: 0, end: total } });
            }}
          />
        ) : (
          <div className="media-composer__file">
            {current.kind === "audio" ? <Headphones size={64} /> : <FileText size={64} />}
            <strong>{current.file.name}</strong>
            <span>{fileSize(current.file.size)} · {(current.file.name.split(".").pop() || "").toUpperCase()}</span>
            {current.kind === "audio" ? <audio src={current.url} controls /> : null}
          </div>
        )}
      </div>

      <div className="media-composer__caption">
        <div className="media-composer__caption-box">
          <input
            ref={captionRef}
            value={current.caption}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Type a message"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            maxLength={1024}
            autoFocus
          />
          <span ref={emojiBtnRef}>
            <IconButton icon={Smile} label="Emoji" active={emojiOpen} onClick={() => setEmojiOpen((value) => !value)} />
          </span>
          {current.kind === "image" || current.kind === "video" ? (
            <button
              type="button"
              className={`icon-btn view-once-toggle ${current.viewOnce ? "is-on" : ""}`}
              aria-pressed={current.viewOnce}
              aria-label={current.viewOnce ? "View once on" : "View once off"}
              data-tooltip="View once"
              onClick={toggleViewOnce}
            >
              <ViewOnceIcon size={24} opened={false} />
            </button>
          ) : null}
          {emojiOpen ? (
            <EmojiPicker
              className="emoji-picker--caption"
              ignoreRefs={[emojiBtnRef]}
              onClose={() => setEmojiOpen(false)}
              onPick={(emoji) => {
                setCaption(current.caption + emoji);
                captionRef.current?.focus();
              }}
            />
          ) : null}
        </div>
      </div>

      <div className="media-composer__bottom">
        <div className="media-composer__thumbs" role="listbox" aria-label="Selected files">
          {items.map((item, index) => (
            <div key={item.id} className={`thumb ${index === active ? "is-active" : ""}`} role="option" aria-selected={index === active}>
              <button type="button" className="thumb__select" onClick={() => setActive(index)} aria-label={`Preview ${item.file.name}`}>
                {item.viewOnce ? <span className="thumb__once"><ViewOnceIcon size={14} /></span> : null}
                {item.kind === "image" ? (
                  <img src={item.url} alt="" />
                ) : item.kind === "video" ? (
                  <video src={`${item.url}#t=0.1`} muted preload="metadata" />
                ) : item.kind === "audio" ? (
                  <Headphones size={22} />
                ) : (
                  <FileText size={22} />
                )}
              </button>
              <button type="button" className="thumb__remove" onClick={() => remove(item.id)} aria-label={`Remove ${item.file.name}`}>
                <X size={13} />
              </button>
            </div>
          ))}
          {items.length < MAX_ITEMS ? (
            <button type="button" className="thumb thumb--add" onClick={() => addRef.current?.click()} aria-label="Add more files">
              <Plus size={24} />
            </button>
          ) : null}
          <input ref={addRef} type="file" accept={accept} multiple hidden onChange={addMore} />
        </div>
        <div className="media-composer__send">
          <button
            type="button"
            className={`fab fab--send ${busy ? "is-busy" : ""}`}
            onClick={send}
            disabled={busy}
            aria-label={`Send ${items.length} item${items.length > 1 ? "s" : ""}`}
            title={items.length > 1 ? `${items.length} items · ${fileSize(items.reduce((sum, item) => sum + item.file.size, 0))}` : undefined}
          >
            <Send size={24} />
            <span className="fab__count">{items.length}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
