import { useEffect, useRef, useState } from "react";
import { Clock3, Heart, Plus, Trash2 } from "lucide-react";
import { errorMessage, mediaUrl } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks";
import { toast } from "../../services/toast";
import { SearchInput, Spinner } from "../common/ui";
import { forgetSticker, makeStickerFile, rememberSticker, savedStickers, stickerFile } from "../../utils/stickers";

const GIF_CHIPS = ["Haha", "Love", "Sad", "Wow", "Hi", "Thank you", "Party", "OK", "Angry", "Dance"];

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
      .catch(
        (error) =>
          !cancelled &&
          setState({
            term,
            items: [],
            // Server without a GIPHY key: friendly text, recent GIFs still work.
            error: error?.response?.status === 503 ? "GIF search isn't turned on for this server yet." : errorMessage(error, "Couldn't load GIFs."),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [term]);
  const loading = state.term !== term;
  const recentMatches = term ? recent.filter((gif) => (gif.title || "").toLowerCase().includes(term.toLowerCase())) : [];
  return (
    <>
      <div className="emoji-picker__search" onMouseDown={(event) => event.stopPropagation()}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search GIFs" />
      </div>
      <div className="gif-chips" onMouseDown={(event) => event.stopPropagation()}>
        {GIF_CHIPS.map((chip) => (
          <button key={chip} type="button" className={`chip ${query === chip ? "is-active" : ""}`} onClick={() => setQuery(query === chip ? "" : chip)}>
            {chip}
          </button>
        ))}
      </div>
      <div className="emoji-picker__grid gif-grid">
        {term && state.error && recentMatches.length ? (
          recentMatches.map((gif) => (
            <button key={gif.id} type="button" className="gif-grid__item" onClick={() => onPick(gif)} title={gif.title} aria-label={gif.title || "GIF"}>
              <video src={gif.preview} poster={gif.still || undefined} autoPlay loop muted playsInline />
            </button>
          ))
        ) : null}
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

let packsPromise = null;
/** Built-in sticker packs (public/stickers/packs.json), loaded once. */
function loadPacks() {
  if (!packsPromise) {
    packsPromise = fetch("/stickers/packs.json")
      .then((response) => (response.ok ? response.json() : { packs: [] }))
      .then((data) => data.packs || [])
      .catch(() => {
        packsPromise = null;
        return [];
      });
  }
  return packsPromise;
}

/**
 * Sticker tab, WhatsApp style: a row of tabs (Recent, ♥ My stickers and
 * each built-in pack), a search box that finds stickers by meaning
 * ("love", "lol", "salam"), and "Create" to turn a photo into a sticker.
 */
export function StickerPanel({ onPick }) {
  const [items, setItems] = useState(savedStickers);
  const [recent, setRecent] = useState([]);
  const [packs, setPacks] = useState([]);
  const [tab, setTab] = useState("packs:first");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    chatApi
      .recentStickers()
      .then((urls) => !cancelled && setRecent(urls))
      .catch(() => {});
    loadPacks().then((list) => !cancelled && setPacks(list));
    return () => {
      cancelled = true;
    };
  }, []);

  async function sendUrl(url, name) {
    setBusy(true);
    try {
      const blob = await fetch(url).then((response) => {
        if (!response.ok) throw new Error("download failed");
        return response.blob();
      });
      onPick(new File([blob], name || url.split("/").pop() || "sticker.webp", { type: blob.type || "image/webp" }));
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
      setTab("mine");
      onPick(sticker);
    } catch {
      toast.error("Couldn't make a sticker from that file.");
    } finally {
      setBusy(false);
    }
  }

  const term = query.trim().toLowerCase();
  const activeTab = tab === "packs:first" ? (recent.length ? "recent" : packs[0]?.id || "mine") : tab;
  const found = term
    ? packs.flatMap((pack) => pack.stickers.filter((sticker) => sticker.tags.split(/\s+/).some((tag) => tag.startsWith(term)) || pack.name.toLowerCase().includes(term)))
    : null;
  const pack = packs.find((item) => item.id === activeTab);
  const packSticker = (sticker) => (
    <span key={sticker.id} className="sticker-grid__item">
      <button type="button" onClick={() => sendUrl(sticker.file, `${sticker.id.replace("/", "-")}.webp`)} aria-label={`Send ${sticker.tags.split(" ")[0]} sticker`} disabled={busy}>
        <img src={sticker.file} alt="" draggable={false} loading="lazy" />
      </button>
    </span>
  );

  return (
    <>
      <div className="emoji-picker__search sticker-search" onMouseDown={(event) => event.stopPropagation()}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search stickers (love, lol, salam…)" autoFocus={false} />
      </div>
      {!term ? (
        <div className="sticker-tabs" role="tablist" aria-label="Sticker packs">
          {recent.length ? (
            <button type="button" role="tab" aria-selected={activeTab === "recent"} className={activeTab === "recent" ? "is-active" : ""} onClick={() => setTab("recent")} aria-label="Recent stickers">
              <Clock3 size={20} />
            </button>
          ) : null}
          <button type="button" role="tab" aria-selected={activeTab === "mine"} className={activeTab === "mine" ? "is-active" : ""} onClick={() => setTab("mine")} aria-label="My stickers">
            <Heart size={20} />
          </button>
          {packs.map((item) => (
            <button key={item.id} type="button" role="tab" aria-selected={activeTab === item.id} className={activeTab === item.id ? "is-active" : ""} onClick={() => setTab(item.id)} aria-label={item.name} title={item.name}>
              <img src={item.icon} alt="" draggable={false} />
            </button>
          ))}
        </div>
      ) : null}
      <div className="emoji-picker__grid sticker-grid">
        {found ? (
          found.length ? found.map(packSticker) : <p className="sticker-grid__hint">No stickers for "{query}"</p>
        ) : activeTab === "recent" ? (
          <>
            <h4 className="sticker-grid__title">Recent</h4>
            {recent.map((url) => (
              <span key={url} className="sticker-grid__item">
                <button type="button" onClick={() => sendUrl(mediaUrl(url))} aria-label="Send sticker" disabled={busy}>
                  <img src={mediaUrl(url)} alt="" draggable={false} loading="lazy" />
                </button>
              </span>
            ))}
          </>
        ) : activeTab === "mine" ? (
          <>
            <h4 className="sticker-grid__title">My stickers</h4>
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
            {!items.length ? <p className="sticker-grid__hint">Tap Create to turn any photo into a sticker, or long-press a sticker in a chat → "Add to my stickers".</p> : null}
          </>
        ) : pack ? (
          <>
            <h4 className="sticker-grid__title">{pack.name}</h4>
            {pack.stickers.map(packSticker)}
          </>
        ) : null}
        <input ref={inputRef} type="file" accept="image/*" hidden onChange={create} />
      </div>
    </>
  );
}
