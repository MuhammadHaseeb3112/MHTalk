import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { loadImage, renderMarkup } from "./markup";

const PENCIL_WIDTH = 0.008;
const BLUR_WIDTH = 0.06;
const RECT_WIDTH = 0.006;
const TEXT_SIZE = 0.06;

/**
 * Interactive photo preview for the media composer. Draws the photo plus its
 * markup on a canvas and turns pointer input into operations:
 * pencil / blur strokes, rectangles, text (typed in place) and dragging of
 * existing text, emoji and rectangles when no tool is selected.
 */
export default function MarkupCanvas({ url, alt, ops, tool, color, onChange }) {
  const boxRef = useRef(null);
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const draftRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef([]);
  const opsRef = useRef(ops);
  const [loadedUrl, setLoadedUrl] = useState(null);
  const ready = loadedUrl === url;
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [text, setText] = useState(null); // { x, y, value }

  useEffect(() => {
    opsRef.current = ops;
  }, [ops]);

  // Load the photo.
  useEffect(() => {
    let alive = true;
    loadImage(url)
      .then((img) => {
        if (!alive) return;
        imgRef.current = img;
        setLoadedUrl(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [url]);

  // Fit the photo inside the preview area (never upscale).
  useLayoutEffect(() => {
    const node = boxRef.current;
    if (!node || !ready) return undefined;
    const fit = () => {
      const img = imgRef.current;
      const scale = Math.min(node.clientWidth / img.naturalWidth, node.clientHeight / img.naturalHeight, 1);
      setSize({ w: Math.max(1, Math.floor(img.naturalWidth * scale)), h: Math.max(1, Math.floor(img.naturalHeight * scale)) });
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    return () => observer.disconnect();
  }, [ready]);

  const draw = useCallback(
    (list) => {
      const canvas = canvasRef.current;
      const img = imgRef.current;
      if (!canvas || !img || !size.w) return;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(size.w * dpr)) {
        canvas.width = Math.round(size.w * dpr);
        canvas.height = Math.round(size.h * dpr);
      }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      hitRef.current = renderMarkup(ctx, img, list, size.w, size.h);
    },
    [size],
  );

  useEffect(() => {
    if (ready) draw(ops);
  }, [ready, ops, draw]);

  const point = (event) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    };
  };

  const commitText = () => {
    if (text?.value.trim()) {
      onChange([...opsRef.current, { type: "text", x: text.x, y: text.y, text: text.value.trim(), color, size: TEXT_SIZE }]);
    }
    setText(null);
  };

  const onPointerDown = (event) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    const p = point(event);
    if (tool === "text") {
      // Keep the browser from moving focus away from the text box we open.
      event.preventDefault();
      if (text) commitText();
      setText({ x: p.x, y: p.y, value: "" });
      return;
    }
    canvasRef.current.setPointerCapture(event.pointerId);
    if (tool === "draw" || tool === "blur") {
      draftRef.current = { type: tool === "draw" ? "stroke" : "blur", color, width: tool === "draw" ? PENCIL_WIDTH : BLUR_WIDTH, points: [p] };
    } else if (tool === "rect") {
      draftRef.current = { type: "rect", color, width: RECT_WIDTH, x: p.x, y: p.y, w: 0, h: 0 };
    } else {
      // No tool: pick up a text / emoji / rectangle under the pointer.
      const hit = [...hitRef.current].reverse().find((box) => p.x >= box.x && p.x <= box.x + box.w && p.y >= box.y && p.y <= box.y + box.h);
      if (hit) dragRef.current = { index: hit.index, start: p, origin: { ...opsRef.current[hit.index] }, moved: false };
    }
  };

  const onPointerMove = (event) => {
    const p = point(event);
    const draft = draftRef.current;
    if (draft) {
      if (draft.type === "rect") {
        draft.w = p.x - draft.x;
        draft.h = p.y - draft.y;
      } else {
        draft.points.push(p);
      }
      draw([...opsRef.current, draft]);
      return;
    }
    const drag = dragRef.current;
    if (drag) {
      drag.moved = true;
      const dx = p.x - drag.start.x;
      const dy = p.y - drag.start.y;
      const moved = { ...drag.origin, x: drag.origin.x + dx, y: drag.origin.y + dy };
      drag.current = moved;
      draw(opsRef.current.map((op, index) => (index === drag.index ? moved : op)));
    }
  };

  const onPointerUp = () => {
    const draft = draftRef.current;
    draftRef.current = null;
    if (draft) {
      const tiny = draft.type === "rect" && Math.abs(draft.w) < 0.01 && Math.abs(draft.h) < 0.01;
      if (!tiny) onChange([...opsRef.current, draft]);
      else draw(opsRef.current);
      return;
    }
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag?.moved && drag.current) {
      onChange(opsRef.current.map((op, index) => (index === drag.index ? drag.current : op)));
    }
  };

  const cursor = tool === "text" ? "text" : tool ? "crosshair" : "default";

  return (
    <div ref={boxRef} className="markup-box">
      {ready ? (
        <div className="markup" style={{ width: size.w, height: size.h }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={alt}
            style={{ width: size.w, height: size.h, cursor, touchAction: tool ? "none" : "auto" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          />
          {text ? (
            <input
              className="markup__text"
              style={{ left: text.x * size.w, top: text.y * size.h, color, fontSize: TEXT_SIZE * size.w }}
              value={text.value}
              autoFocus
              placeholder="Type…"
              aria-label="Text on photo"
              onChange={(event) => setText({ ...text, value: event.target.value })}
              onBlur={commitText}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitText();
                }
                if (event.key === "Escape") setText(null);
              }}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
