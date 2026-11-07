import { useEffect, useState } from "react";
import { ForwardDialog } from "../conversation/dialogs";
import { sendFile, sendSticker, sendText } from "../../store/actions";

const SHARE_CACHE = "mhtalk-share";

async function readShared() {
  if (!("caches" in window)) return null;
  const cache = await caches.open(SHARE_CACHE);
  const metaResponse = await cache.match("/__share/meta");
  if (!metaResponse) return null;
  const meta = await metaResponse.json();
  const files = [];
  for (const item of meta.files || []) {
    const response = await cache.match(item.key);
    if (!response) continue;
    const blob = await response.blob();
    files.push(new File([blob], item.name, { type: item.type || blob.type }));
  }
  const text = [meta.title, meta.text, meta.url].filter(Boolean).filter((v, i, all) => all.indexOf(v) === i).join("\n");
  return { files, text };
}

async function clearShared() {
  try {
    await caches.delete(SHARE_CACHE);
  } catch {
    /* ignore */
  }
}

function describe({ files }) {
  if (!files.length) return "Send message to";
  const gifs = files.filter((file) => file.type === "image/gif").length;
  if (files.length === 1) return gifs ? "Send GIF to" : file1Label(files[0]);
  return `Send ${files.length} files to`;
}

function file1Label(file) {
  if (file.type === "image/webp") return "Send sticker to";
  if (file.type.startsWith("image/")) return "Send photo to";
  if (file.type.startsWith("video/")) return "Send video to";
  return "Send file to";
}

/**
 * Things shared into the installed app ("Share → MHTalk" from the gallery,
 * Gboard's GIF/sticker share, other apps) open a "Send to…" chat picker.
 */
export default function ShareReceiver() {
  const [shared, setShared] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("share")) return;
    params.delete("share");
    const query = params.toString();
    window.history.replaceState(window.history.state, "", window.location.pathname + (query ? `?${query}` : "") + window.location.hash);
    readShared()
      .then((data) => {
        if (data && (data.files.length || data.text)) setShared(data);
        else clearShared();
      })
      .catch(() => clearShared());
  }, []);

  if (!shared) return null;

  const close = () => {
    setShared(null);
    clearShared();
  };

  const send = async (roomIds) => {
    for (const roomId of roomIds) {
      for (const file of shared.files) {
        if (file.type === "image/webp") await sendSticker(roomId, file);
        else await sendFile(roomId, file);
      }
      if (shared.text) await sendText(roomId, shared.text);
    }
  };

  return <ForwardDialog title={describe(shared)} onClose={close} onSend={send} />;
}
