/**
 * Photo markup used by the media composer (WhatsApp-style editor):
 * freehand pencil, text, rectangles, blur brush and emoji stickers.
 *
 * Operations are stored in normalised image coordinates (0..1 of width /
 * height; sizes relative to the image width), so the same list renders on the
 * small on-screen preview and on the full-resolution file that is uploaded.
 */

export const COLORS = ["#ffffff", "#111b21", "#f15c6d", "#ffd279", "#21c063", "#53bdeb", "#a78bfa", "#ff8a3d"];

const EMOJI_FONT = '"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
const TEXT_FONT = 'system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';

/** Longest side of a photo sent in standard quality (HD sends the original). */
export const STANDARD_MAX_SIDE = 1600;

export function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Couldn't read this image."));
    img.src = url;
  });
}

function pixelated(img, width, height) {
  const block = Math.max(6, Math.round(width / 45));
  const small = document.createElement("canvas");
  small.width = Math.max(1, Math.round(width / block));
  small.height = Math.max(1, Math.round(height / block));
  small.getContext("2d").drawImage(img, 0, 0, small.width, small.height);
  const big = document.createElement("canvas");
  big.width = width;
  big.height = height;
  const ctx = big.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(small, 0, 0, width, height);
  return big;
}

function strokePath(ctx, points, width, height) {
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = point.x * width;
    const y = point.y * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (points.length === 1) ctx.lineTo(points[0].x * width + 0.1, points[0].y * height);
}

/**
 * Draw the photo plus every operation at width x height. Returns hit boxes
 * (normalised) for text / emoji / rectangle items so they can be dragged.
 */
export function renderMarkup(ctx, img, ops, width, height, { background } = {}) {
  ctx.clearRect(0, 0, width, height);
  if (background) {
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);
  }
  ctx.drawImage(img, 0, 0, width, height);
  let blurred = null;
  const boxes = [];
  ops.forEach((op, index) => {
    if (!op) return;
    ctx.save();
    if (op.type === "stroke") {
      ctx.strokeStyle = op.color;
      ctx.lineWidth = op.width * width;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      strokePath(ctx, op.points, width, height);
      ctx.stroke();
    } else if (op.type === "blur") {
      blurred = blurred || pixelated(img, width, height);
      const layer = document.createElement("canvas");
      layer.width = width;
      layer.height = height;
      const lctx = layer.getContext("2d");
      lctx.drawImage(blurred, 0, 0);
      lctx.globalCompositeOperation = "destination-in";
      lctx.lineWidth = op.width * width;
      lctx.lineCap = "round";
      lctx.lineJoin = "round";
      strokePath(lctx, op.points, width, height);
      lctx.stroke();
      ctx.drawImage(layer, 0, 0);
    } else if (op.type === "rect") {
      const x = Math.min(op.x, op.x + op.w);
      const y = Math.min(op.y, op.y + op.h);
      const w = Math.abs(op.w);
      const h = Math.abs(op.h);
      ctx.strokeStyle = op.color;
      ctx.lineWidth = op.width * width;
      ctx.lineJoin = "round";
      ctx.strokeRect(x * width, y * height, w * width, h * height);
      boxes.push({ index, x, y, w, h });
    } else if (op.type === "text" || op.type === "emoji") {
      const size = op.size * width;
      ctx.font = op.type === "emoji" ? `${size}px ${EMOJI_FONT}` : `600 ${size}px ${TEXT_FONT}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const x = op.x * width;
      const y = op.y * height;
      if (op.type === "text") {
        // dark outline keeps any colour readable on any photo
        ctx.lineWidth = Math.max(2, size * 0.12);
        ctx.strokeStyle = op.color === "#111b21" ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.55)";
        ctx.lineJoin = "round";
        ctx.strokeText(op.text, x, y);
        ctx.fillStyle = op.color;
      }
      ctx.fillText(op.text, x, y);
      const textWidth = ctx.measureText(op.text).width;
      boxes.push({ index, x: (x - textWidth / 2) / width, y: (y - size * 0.6) / height, w: textWidth / width, h: (size * 1.2) / height });
    }
    ctx.restore();
  });
  return boxes;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Couldn't save this image."))), type, quality);
  });
}

function renamed(name, extension) {
  const base = name.replace(/\.[^.]+$/, "") || "photo";
  return `${base}.${extension}`;
}

/** The photo with its markup at full resolution, as PNG (copy / download / crop). */
export async function composedBlob(item, type = "image/png") {
  const img = await loadImage(item.url);
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  renderMarkup(canvas.getContext("2d"), img, item.ops || [], canvas.width, canvas.height, {
    background: type === "image/jpeg" ? "#ffffff" : undefined,
  });
  return canvasToBlob(canvas, type, 0.92);
}

/**
 * The file actually uploaded for a photo. Standard quality (WhatsApp's
 * default) resizes to STANDARD_MAX_SIDE and re-encodes as JPEG, which cuts
 * upload time and storage several times over. HD keeps the full resolution.
 * Untouched small photos and GIFs are sent as they are.
 */
export async function preparePhoto(item) {
  const file = item.file;
  if (file.type === "image/gif" || file.type === "image/svg+xml") return file;
  const hasMarkup = Boolean(item.ops?.length);
  const img = await loadImage(item.url);
  const longest = Math.max(img.naturalWidth, img.naturalHeight);
  const scale = !item.hd && longest > STANDARD_MAX_SIDE ? STANDARD_MAX_SIDE / longest : 1;
  if (!hasMarkup && scale === 1 && (item.hd || file.size <= 1.5 * 1024 * 1024)) return file;

  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
  const keepPng = item.hd && file.type === "image/png";
  const type = keepPng ? "image/png" : "image/jpeg";
  renderMarkup(canvas.getContext("2d"), img, item.ops || [], canvas.width, canvas.height, {
    background: keepPng ? undefined : "#ffffff",
  });
  const blob = await canvasToBlob(canvas, type, item.hd ? 0.92 : 0.82);
  // Never send a "compressed" file that came out bigger than the original.
  if (!hasMarkup && blob.size >= file.size) return file;
  return new File([blob], renamed(file.name, keepPng ? "png" : "jpg"), { type, lastModified: Date.now() });
}
