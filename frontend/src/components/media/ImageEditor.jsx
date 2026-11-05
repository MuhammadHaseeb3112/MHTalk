import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, RotateCcw, RotateCw, Smile, Trash2, X } from "lucide-react";
import EmojiPicker from "../conversation/EmojiPicker";
import { IconButton } from "../common/ui";

const ASPECTS = [
  { id: "free", label: "Free" },
  { id: "original", label: "Original" },
  { id: "1:1", label: "Square", value: 1 },
  { id: "4:3", label: "4:3", value: 4 / 3 },
  { id: "3:4", label: "3:4", value: 3 / 4 },
  { id: "16:9", label: "16:9", value: 16 / 9 },
];

/**
 * Crop / rotate / zoom editor with emoji stickers. The original file is
 * untouched until "Done" — then a new JPEG/PNG File is produced.
 */
export default function ImageEditor({ file, url, onCancel, onApply }) {
  const stageRef = useRef(null);
  const imgRef = useRef(null);
  const emojiBtnRef = useRef(null);
  const [natural, setNatural] = useState(null);
  const [stage, setStage] = useState({ w: 600, h: 420 });
  const [rotation, setRotation] = useState(0); // multiples of 90
  const [aspect, setAspect] = useState("free");
  const [crop, setCrop] = useState(null); // free crop box size {w, h} (null = whole photo)
  const [zoom, setZoom] = useState(1); // multiplier over cover-fit
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [stickers, setStickers] = useState([]);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const dragRef = useRef(null);

  useLayoutEffect(() => {
    const node = stageRef.current;
    if (!node) return undefined;
    const update = () => setStage({ w: node.clientWidth - 40, h: node.clientHeight - 40 });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const rotated = useMemo(
    () => (natural ? (rotation % 180 === 0 ? { w: natural.w, h: natural.h } : { w: natural.h, h: natural.w }) : null),
    [natural, rotation],
  );
  let frameW;
  let frameH;
  let scale;
  // Free crop: the whole photo fits in the stage, and you pull the corners /
  // edges of the crop box in (like a phone's photo editor).
  const contain = rotated ? Math.min(stage.w / rotated.w, stage.h / rotated.h) : 1;
  const maxW = rotated ? Math.min(stage.w, rotated.w * contain * zoom) : stage.w;
  const maxH = rotated ? Math.min(stage.h, rotated.h * contain * zoom) : stage.h;
  if (aspect === "free") {
    frameW = Math.max(60, Math.min(maxW, crop?.w ?? maxW));
    frameH = Math.max(60, Math.min(maxH, crop?.h ?? maxH));
    scale = contain * zoom;
  } else {
    const ratio = aspect === "original" ? (rotated ? rotated.w / rotated.h : 1) : ASPECTS.find((item) => item.id === aspect).value;
    frameW = stage.w;
    frameH = frameW / ratio;
    if (frameH > stage.h) {
      frameH = stage.h;
      frameW = frameH * ratio;
    }
    const baseScale = rotated ? Math.max(frameW / rotated.w, frameH / rotated.h) : 1;
    scale = baseScale * zoom;
  }

  const clampPan = useCallback(
    (next) => {
      if (!rotated) return next;
      const maxX = Math.max(0, (rotated.w * scale - frameW) / 2);
      const maxY = Math.max(0, (rotated.h * scale - frameH) / 2);
      return { x: Math.max(-maxX, Math.min(maxX, next.x)), y: Math.max(-maxY, Math.min(maxY, next.y)) };
    },
    [rotated, scale, frameW, frameH],
  );

  // The stored pan may be out of range after zoom/rotate/aspect changes; clamp when used.
  const view = clampPan(pan);

  function onPointerDown(event) {
    if (event.target.closest(".sticker")) return;
    const handle = event.target.closest("[data-handle]")?.dataset.handle;
    if (handle) {
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = { type: "resize", handle, x: event.clientX, y: event.clientY, start: { w: frameW, h: frameH } };
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { type: "pan", x: event.clientX, y: event.clientY, start: view };
  }
  function onPointerMove(event) {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.type === "resize") {
      // The box stays centred, so each edge moves by the drag and the size by twice that.
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      let w = drag.start.w;
      let h = drag.start.h;
      if (drag.handle.includes("e")) w += dx * 2;
      if (drag.handle.includes("w")) w -= dx * 2;
      if (drag.handle.includes("s")) h += dy * 2;
      if (drag.handle.includes("n")) h -= dy * 2;
      setCrop({ w: Math.max(60, Math.min(maxW, w)), h: Math.max(60, Math.min(maxH, h)) });
    } else if (drag.type === "pan") {
      setPan(clampPan({ x: drag.start.x + event.clientX - drag.x, y: drag.start.y + event.clientY - drag.y }));
    } else if (drag.type === "sticker") {
      const dx = (event.clientX - drag.x) / frameW;
      const dy = (event.clientY - drag.y) / frameH;
      setStickers((items) => items.map((item) => (item.id === drag.id ? { ...item, x: Math.min(1, Math.max(0, drag.start.x + dx)), y: Math.min(1, Math.max(0, drag.start.y + dy)) } : item)));
    }
  }
  function onPointerUp() {
    dragRef.current = null;
  }

  function rotate(direction) {
    setRotation((value) => (value + direction * 90 + 360) % 360);
    setPan({ x: 0, y: 0 });
    setCrop(null);
  }

  async function apply() {
    if (!natural) return;
    setBusy(true);
    const longest = Math.min(2560, Math.max(rotated.w, rotated.h) * zoom);
    const k = Math.min(longest / Math.max(frameW, frameH), 1 / scale); // never upscale beyond natural pixels
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(frameW * k));
    canvas.height = Math.max(1, Math.round(frameH * k));
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.translate(canvas.width / 2 + view.x * k, canvas.height / 2 + view.y * k);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(scale * k, scale * k);
    ctx.drawImage(imgRef.current, -natural.w / 2, -natural.h / 2);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    stickers.forEach((sticker) => {
      const size = sticker.size * canvas.width;
      ctx.font = `${size}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(sticker.emoji, sticker.x * canvas.width, sticker.y * canvas.height);
    });
    const type = file.type === "image/png" ? "image/png" : "image/jpeg";
    canvas.toBlob(
      (blob) => {
        setBusy(false);
        if (!blob) return;
        const name = file.name.replace(/\.[^.]+$/, "") + (type === "image/png" ? ".png" : ".jpg");
        onApply(new File([blob], name, { type, lastModified: Date.now() }));
      },
      type,
      0.92,
    );
  }

  return (
    <div className="editor">
      <div className="editor__toolbar">
        <IconButton icon={X} label="Cancel editing" onClick={onCancel} />
        <div className="editor__aspects" role="radiogroup" aria-label="Crop ratio">
          {ASPECTS.map((item) => (
            <button key={item.id} type="button" role="radio" aria-checked={aspect === item.id} className={`chip ${aspect === item.id ? "is-active" : ""}`} onClick={() => { setAspect(item.id); setPan({ x: 0, y: 0 }); setCrop(null); }}>
              {item.label}
            </button>
          ))}
        </div>
        <IconButton icon={RotateCcw} label="Rotate left" onClick={() => rotate(-1)} />
        <IconButton icon={RotateCw} label="Rotate right" onClick={() => rotate(1)} />
        <span ref={emojiBtnRef}>
          <IconButton icon={Smile} label="Add emoji" active={emojiOpen} onClick={() => setEmojiOpen((value) => !value)} />
        </span>
        <button type="button" className="btn btn--primary" onClick={apply} disabled={busy || !natural}>
          <Check size={18} /> Done
        </button>
      </div>
      <div className="editor__stage" ref={stageRef}>
        <div
          className={`editor__frame ${aspect === "free" ? "is-free" : ""}`}
          style={{ width: frameW, height: frameH }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onWheel={(event) => setZoom((value) => Math.min(4, Math.max(1, value - event.deltaY * 0.0015)))}
        >
          <img
            ref={imgRef}
            src={url}
            alt="Editing"
            draggable={false}
            onLoad={(event) => setNatural({ w: event.currentTarget.naturalWidth, h: event.currentTarget.naturalHeight })}
            style={
              natural
                ? {
                    width: natural.w,
                    height: natural.h,
                    transform: `translate(-50%, -50%) translate(${view.x}px, ${view.y}px) rotate(${rotation}deg) scale(${scale})`,
                  }
                : { opacity: 0 }
            }
          />
          {stickers.map((sticker) => (
            <span
              key={sticker.id}
              className="sticker emoji"
              style={{ left: `${sticker.x * 100}%`, top: `${sticker.y * 100}%`, fontSize: sticker.size * frameW }}
              onPointerDown={(event) => {
                event.stopPropagation();
                event.currentTarget.parentElement.setPointerCapture(event.pointerId);
                dragRef.current = { type: "sticker", id: sticker.id, x: event.clientX, y: event.clientY, start: { x: sticker.x, y: sticker.y } };
              }}
              onDoubleClick={() => setStickers((items) => items.filter((item) => item.id !== sticker.id))}
              title="Drag to move · double-click to remove"
            >
              {sticker.emoji}
            </span>
          ))}
          <span className="editor__grid" aria-hidden />
          {aspect === "free"
            ? ["n", "s", "e", "w", "nw", "ne", "sw", "se"].map((handle) => (
                <span key={handle} className={`editor__handle editor__handle--${handle}`} data-handle={handle} aria-hidden />
              ))
            : null}
        </div>
        {emojiOpen ? (
          <EmojiPicker
            className="emoji-picker--editor"
            ignoreRefs={[emojiBtnRef]}
            onClose={() => setEmojiOpen(false)}
            onPick={(emoji) => {
              setStickers((items) => [...items, { id: Date.now(), emoji, x: 0.5, y: 0.5, size: 0.14 }]);
              setEmojiOpen(false);
            }}
          />
        ) : null}
      </div>
      <div className="editor__footer">
        <label className="editor__zoom">
          <span>Zoom</span>
          <input type="range" min="1" max="4" step="0.01" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
        </label>
        {stickers.length ? (
          <button type="button" className="btn btn--text" onClick={() => setStickers([])}>
            <Trash2 size={16} /> Remove emoji
          </button>
        ) : (
          <span className="editor__hint">{aspect === "free" ? "Drag the corners or edges to crop · drag the photo to move" : "Drag to reposition · scroll to zoom"}</span>
        )}
      </div>
    </div>
  );
}
