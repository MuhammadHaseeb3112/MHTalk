const EXT = { "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "video/mp4": "mp4" };

/**
 * Read images (or text) from the system clipboard after a user tap.
 * Mobile keyboards can't paste images into a textarea, so this gives a
 * "Paste" button that works with whatever was copied last.
 */
export async function readClipboardFiles() {
  const clip = navigator.clipboard;
  if (!clip) return { files: [], text: "", error: "Clipboard is not available here (needs HTTPS)." };
  try {
    if (clip.read) {
      const items = await clip.read();
      const files = [];
      let text = "";
      for (const item of items) {
        const media = item.types.find((type) => type.startsWith("image/") || type.startsWith("video/"));
        if (media) {
          const blob = await item.getType(media);
          files.push(new File([blob], `pasted-${files.length + 1}.${EXT[media] || media.split("/")[1]}`, { type: media }));
        } else if (!text && item.types.includes("text/plain")) {
          text = await (await item.getType("text/plain")).text();
        }
      }
      if (files.length || text) return { files, text };
    }
    const text = clip.readText ? await clip.readText() : "";
    return { files: [], text };
  } catch {
    return { files: [], text: "", error: "Allow clipboard access to paste, or copy the picture again." };
  }
}

/**
 * Shrink a photo for MHTalk AI: a JPEG (max 1280 px) as base64 for the
 * server, plus a small preview (data URL) to show in the chat.
 */
export function shrinkImage(file, max = 1280, thumbMax = 360) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const draw = (limit, quality) => {
        const scale = Math.min(1, limit / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", quality);
      };
      const full = draw(max, 0.85);
      const thumb = draw(thumbMax, 0.7);
      URL.revokeObjectURL(url);
      resolve({ mime_type: "image/jpeg", data: full.split(",")[1], thumb });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("This picture can't be opened."));
    };
    img.src = url;
  });
}
