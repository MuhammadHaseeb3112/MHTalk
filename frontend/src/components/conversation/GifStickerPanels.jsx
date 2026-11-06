import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks";
import { toast } from "../../services/toast";
import { SearchInput, Spinner } from "../common/ui";
import { forgetSticker, makeStickerFile, rememberSticker, savedStickers, stickerFile } from "../../utils/stickers";

/** GIF tab: trending + search (GIPHY, through our server). */
export function GifPanel({ onPick }) {
  const [query, setQuery] = useState("");
  const term = useDebouncedValue(query.trim(), 400);
  const [state, setState] = useState({ term: null, items: [], error: "" });
  const [recent, setRecent] = useState([]);
  // GIFs sent or received in your chats, like WhatsApp's "Recent".
  useEffect(() => {
    let cancelled = false;
    chatApi
      .recentGifs()
      .then((items) => !cancelled && setRecent(items))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    chatApi
      .gifs(term)
      .then((data) => !cancelled && setState({ term, items: data.results || [], error: "" }))
      .catch((error) => !cancelled && setState({ term, items: [], error: errorMessage(error, "Couldn't load GIFs.") }));
    return () => {
      cancelled = true;
    };
  }, [term]);
  const loading = state.term !== term;
  return (
    <>
      <div className="emoji-picker__search" onMouseDown={(event) => event.stopPropagation()}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search GIFs via GIPHY" />
      </div>
      <div className="emoji-picker__grid gif-grid">
        {!term && recent.length ? (
          <>
            <p className="gif-grid__label">Recent</p>
            {recent.map((gif) => (
              <button key={gif.id} type="button" className="gif-grid__item" onClick={() => onPick(gif)} title={gif.title} aria-label={gif.title || "GIF"}>
                <video src={gif.preview} poster={gif.still || undefined} autoPlay loop muted playsInline />
              </button>
            ))}
            <p className="gif-grid__label">Trending</p>
          </>
        ) : null}
        {loading ? (
          <div className="gif-grid__status"><Spinner /></div>
        ) : state.error ? (
          <p className="emoji-picker__empty">{state.error}</p>
        ) : state.items.length ? (
          state.items.map((gif) => (
            <button key={gif.id} type="button" className="gif-grid__item" onClick={() => onPick(gif)} title={gif.title} aria-label={gif.title || "GIF"}>
              <video src={gif.preview} poster={gif.still || undefined} autoPlay loop muted playsInline />
            </button>
          ))
        ) : (
          <p className="emoji-picker__empty">No GIFs found</p>
        )}
        <span className="gif-grid__credit">Powered by GIPHY</span>
      </div>
    </>
  );
}

/** Sticker tab: your stickers (saved in this browser) + "Create" from a photo. */
export function StickerPanel({ onPick }) {
  const [items, setItems] = useState(savedStickers);
  const [recent, setRecent] = useState([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  // Stickers from your chats (on every device), like WhatsApp's "Recent".
  useEffect(() => {
    let cancelled = false;
    chatApi
      .recentStickers()
      .then((urls) => !cancelled && setRecent(urls))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  async function sendRecent(url) {
    setBusy(true);
    try {
      const blob = await fetch(mediaUrl(url)).then((response) => {
        if (!response.ok) throw new Error("download failed");
        return response.blob();
      });
      const type = blob.type || "image/webp";
      onPick(new File([blob], url.split("/").pop() || "sticker.webp", { type }));
    } catch {
      toast.error("Couldn't send that sticker.");
    } finally {
      setBusy(false);
    }
  }
  async function create(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const sticker = await makeStickerFile(file);
      await rememberSticker(sticker);
      setItems(savedStickers());
      onPick(sticker);
    } catch {
      toast.error("Couldn't make a sticker from that file.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="emoji-picker__grid sticker-grid">
      <button type="button" className="sticker-grid__create" onClick={() => inputRef.current?.click()} disabled={busy}>
        {busy ? <Spinner /> : <Plus size={26} />}
        <span>Create</span>
      </button>
      {items.map((item) => (
        <span key={item.id} className="sticker-grid__item">
          <button type="button" onClick={() => onPick(stickerFile(item))} aria-label="Send sticker">
            <img src={item.data} alt="" draggable={false} />
          </button>
          <button
            type="button"
            className="sticker-grid__remove"
            aria-label="Remove sticker"
            onClick={() => {
              forgetSticker(item.id);
              setItems(savedStickers());
            }}
          >
            <Trash2 size={12} />
          </button>
        </span>
      ))}
      {recent.length ? <h4 className="sticker-grid__title">Recent</h4> : null}
      {recent.map((url) => (
        <span key={url} className="sticker-grid__item">
          <button type="button" onClick={() => sendRecent(url)} aria-label="Send sticker" disabled={busy}>
            <img src={mediaUrl(url)} alt="" draggable={false} loading="lazy" />
          </button>
        </span>
      ))}
      {!items.length && !recent.length ? <p className="sticker-grid__hint">Tap Create to turn any photo into a sticker.</p> : null}
      <input ref={inputRef} type="file" accept="image/*" hidden onChange={create} />
    </div>
  );
}
