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
