/**
 * Your stickers, kept in this browser (like WhatsApp's "Recent"/"Favourites").
 * A sticker is a 512×512 transparent WebP made from any picture.
 */
const KEY = "mhtalk_stickers";
const MAX = 40;

export function savedStickers() {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function store(list) {
  let next = list.slice(0, MAX);
  // Storage is limited: drop the oldest until it fits.
  while (next.length) {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
      return;
    } catch {
      next = next.slice(0, -1);
    }
  }
}

function toDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export async function rememberSticker(file) {
  const data = await toDataUrl(file);
  const list = savedStickers().filter((item) => item.data !== data);
  store([{ id: `${Date.now()}`, data }, ...list]);
}

export function forgetSticker(id) {
  store(savedStickers().filter((item) => item.id !== id));
}

export function stickerFile(item) {
  const [head, body] = item.data.split(",");
  const type = /data:([^;]+)/.exec(head)?.[1] || "image/webp";
  const bytes = Uint8Array.from(atob(body), (char) => char.charCodeAt(0));
  return new File([bytes], `sticker-${item.id}.${type.includes("png") ? "png" : "webp"}`, { type });
}

/** Any image → 512×512 sticker (fits inside, transparent edges). */
export function makeStickerFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const size = 512;
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");
      const k = Math.min(size / img.naturalWidth, size / img.naturalHeight);
      const w = img.naturalWidth * k;
      const h = img.naturalHeight * k;
      ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob(
        (blob) => {
          if (!blob) return reject(new Error("encode failed"));
          const type = blob.type || "image/png";
          resolve(new File([blob], `sticker-${Date.now()}.${type.includes("webp") ? "webp" : "png"}`, { type }));
        },
        "image/webp",
        0.9,
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("not an image"));
    };
    img.src = url;
  });
}
