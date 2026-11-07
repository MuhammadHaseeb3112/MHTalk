import { useEffect, useMemo, useRef, useState } from "react";
import { Clock3, Delete, Smile, Sticker } from "lucide-react";
import { GifPanel, StickerPanel } from "./GifStickerPanels";
import { useDismiss } from "../../hooks";
import { EMOJI_CATEGORIES, loadEmojiKeywords, recentEmoji, rememberEmoji, searchEmoji } from "../../utils/emoji";
import { SearchInput } from "../common/ui";

/**
 * Emoji panel with category tabs, keyword search and recents.
 * Closes on outside click / Escape (and unmounts when the chat changes).
 */
export default function EmojiPicker({ onPick, onGif = null, onSticker = null, onBackspace = null, onClose, className = "", ignoreRefs = [] }) {
  const [mode, setMode] = useState("emoji"); // emoji | gif | sticker (chat composer only)
  const ref = useRef(null);
  const gridRef = useRef(null);
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState(recentEmoji);
  const [activeTab, setActiveTab] = useState(recent.length ? "recent" : EMOJI_CATEGORIES[0].id);
  useDismiss([ref, ...ignoreRefs], onClose);

  // Full keyword list (every emoji) loads the first time someone searches.
  const [library, setLibrary] = useState(null);
  useEffect(() => {
    if (!query || library) return;
    let cancelled = false;
    loadEmojiKeywords()
      .then((loaded) => !cancelled && setLibrary(loaded))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [query, library]);
  const results = useMemo(() => (query ? searchEmoji(query, library) : null), [query, library]);

  function pick(emoji) {
    rememberEmoji(emoji);
    setRecent(recentEmoji());
    onPick(emoji);
  }

  function jump(id) {
    setActiveTab(id);
    setQuery("");
    window.requestAnimationFrame(() => {
      gridRef.current?.querySelector(`[data-section="${id}"]`)?.scrollIntoView({ block: "start" });
    });
  }

  function onScroll() {
    const grid = gridRef.current;
    if (!grid || query) return;
    const sections = [...grid.querySelectorAll("[data-section]")];
    const top = grid.scrollTop + 8;
    let current = sections[0]?.dataset.section;
    sections.forEach((section) => {
      if (section.offsetTop <= top) current = section.dataset.section;
    });
    if (current && current !== activeTab) setActiveTab(current);
  }

  const tabs = [...(recent.length ? [{ id: "recent", icon: <Clock3 size={18} />, label: "Recent" }] : []), ...EMOJI_CATEGORIES.map((c) => ({ id: c.id, icon: <span className="emoji">{c.icon}</span>, label: c.label }))];

  const modes = onGif || onSticker ? (
    <div className="emoji-picker__modes" role="tablist" aria-label="Emoji, GIFs and stickers">
      <button type="button" role="tab" aria-selected={mode === "emoji"} className={mode === "emoji" ? "is-active" : ""} onClick={() => setMode("emoji")} aria-label="Emoji">
        <Smile size={20} />
      </button>
      {onGif ? (
        <button type="button" role="tab" aria-selected={mode === "gif"} className={mode === "gif" ? "is-active" : ""} onClick={() => setMode("gif")} aria-label="GIFs">
          <span className="emoji-picker__gif-label">GIF</span>
        </button>
      ) : null}
      {onSticker ? (
        <button type="button" role="tab" aria-selected={mode === "sticker"} className={mode === "sticker" ? "is-active" : ""} onClick={() => setMode("sticker")} aria-label="Stickers">
          <Sticker size={20} />
        </button>
      ) : null}
      {onBackspace && mode === "emoji" ? (
        <button type="button" className="emoji-picker__backspace" aria-label="Delete" onClick={onBackspace}>
          <Delete size={20} />
        </button>
      ) : null}
    </div>
  ) : null;

  if (mode !== "emoji") {
    return (
      <div ref={ref} className={`emoji-picker ${className}`} role="dialog" aria-label={mode === "gif" ? "GIFs" : "Stickers"} onMouseDown={(event) => event.target.closest("input") || event.preventDefault()}>
        {mode === "gif" ? <GifPanel onPick={onGif} /> : <StickerPanel onPick={onSticker} />}
        {modes}
      </div>
    );
  }

  return (
    <div ref={ref} className={`emoji-picker ${className}`} role="dialog" aria-label="Emoji picker" onMouseDown={(event) => event.preventDefault()}>
      <div className="emoji-picker__tabs" role="tablist">
        {tabs.map((tab) => (
          <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} aria-label={tab.label} title={tab.label} className={activeTab === tab.id ? "is-active" : ""} onClick={() => jump(tab.id)}>
            {tab.icon}
          </button>
        ))}
      </div>
      <div className="emoji-picker__search" onMouseDown={(event) => event.stopPropagation()}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search emoji" />
      </div>
      <div className="emoji-picker__grid" ref={gridRef} onScroll={onScroll}>
        {results ? (
          results.length ? (
            <div className="emoji-picker__section">
              <div className="emoji-picker__cells">
                {results.map((emoji) => (
                  <button key={emoji} type="button" className="emoji" onClick={() => pick(emoji)}>{emoji}</button>
                ))}
              </div>
            </div>
          ) : (
            <p className="emoji-picker__empty">No emoji found</p>
          )
        ) : (
          <>
            {recent.length ? (
              <div className="emoji-picker__section" data-section="recent">
                <h4>Recent</h4>
                <div className="emoji-picker__cells">
                  {recent.map((emoji) => (
                    <button key={`r-${emoji}`} type="button" className="emoji" onClick={() => pick(emoji)}>{emoji}</button>
                  ))}
                </div>
              </div>
            ) : null}
            {EMOJI_CATEGORIES.map((category) => (
              <div key={category.id} className="emoji-picker__section" data-section={category.id}>
                <h4>{category.label}</h4>
                <div className="emoji-picker__cells">
                  {category.emojis.map((emoji, index) => (
                    <button key={`${emoji}-${index}`} type="button" className="emoji" onClick={() => pick(emoji)}>{emoji}</button>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
      {modes}
    </div>
  );
}
