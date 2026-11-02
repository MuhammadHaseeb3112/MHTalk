import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { messageApi } from "../api/endpoints";

/** Value that only updates after `delay` ms without changes (search inputs). */
export function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Call `handler` on mousedown outside any of the given refs, and on Escape. */
export function useDismiss(refs, handler, active = true) {
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });
  useEffect(() => {
    if (!active) return undefined;
    const list = Array.isArray(refs) ? refs : [refs];
    const onPointer = (event) => {
      if (list.some((ref) => ref.current && ref.current.contains(event.target))) return;
      handlerRef.current(event);
    };
    const onKey = (event) => {
      if (event.key === "Escape") handlerRef.current(event);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer, { passive: true });
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
    // refs are stable objects
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

/**
 * Object URL for a File/Blob, revoked when the file changes or the
 * component unmounts (revocation is deferred so StrictMode's dev-only
 * unmount/remount cycle does not break the preview).
 */
export function useObjectUrl(file) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  const timer = useRef(null);
  useEffect(() => {
    window.clearTimeout(timer.current);
    return () => {
      if (!url) return;
      timer.current = window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
  }, [url]);
  return url;
}

/** Re-render every `ms` (relative timestamps like "last seen"). */
export function useTicker(ms = 60000) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
}

/** Stable callback that always sees the latest props/state. */
export function useEvent(handler) {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  return useCallback((...args) => ref.current(...args), []);
}

/** Number of starred messages in a chat (shown next to "Starred messages"). */
export function useStarredCount(roomId) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () =>
      messageApi
        .starred()
        .then((rows) => alive && setCount(rows.filter((row) => Number(row.room_id) === Number(roomId)).length))
        .catch(() => {});
    load();
    window.addEventListener("mhtalk:starred-changed", load);
    return () => {
      alive = false;
      window.removeEventListener("mhtalk:starred-changed", load);
    };
  }, [roomId]);
  return count;
}
