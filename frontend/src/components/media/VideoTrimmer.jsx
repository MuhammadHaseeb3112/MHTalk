import { useEffect, useRef, useState } from "react";

const fmt = (seconds) => {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

/** A few still frames along the video for the strip (like WhatsApp). */
function useFilmstrip(url, duration, count = 8) {
  const [frames, setFrames] = useState([]);
  useEffect(() => {
    if (!url || !duration) return undefined;
    let cancelled = false;
    const video = document.createElement("video");
    video.muted = true;
    video.preload = "auto";
    video.playsInline = true;
    video.src = url;
    const canvas = document.createElement("canvas");
    const shots = [];
    const grab = (index) => {
      if (cancelled || index >= count) {
        if (!cancelled) setFrames(shots.slice());
        return;
      }
      const at = Math.min(duration - 0.05, (duration * (index + 0.5)) / count);
      const onSeeked = () => {
        video.removeEventListener("seeked", onSeeked);
        const scale = 72 / Math.max(1, video.videoHeight);
        canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
        canvas.height = 72;
        try {
          canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
          shots.push(canvas.toDataURL("image/jpeg", 0.6));
        } catch {
          shots.push("");
        }
        grab(index + 1);
      };
      video.addEventListener("seeked", onSeeked);
      video.currentTime = Math.max(0, at);
    };
    video.addEventListener("loadeddata", () => grab(0), { once: true });
    return () => {
      cancelled = true;
      video.removeAttribute("src");
      video.load();
    };
  }, [url, duration, count]);
  return frames;
}

/**
 * Pick the part of a video to send: drag the left / right handles.
 * ``value`` is { start, end } in seconds; ``maxLength`` limits the length
 * (status videos: 60 s like WhatsApp).
 */
export default function VideoTrimmer({ url, duration, value, onChange, maxLength = null, sizeBytes = 0 }) {
  const barRef = useRef(null);
  const frames = useFilmstrip(url, duration);
  if (!duration) return null;
  const start = value?.start ?? 0;
  const end = value?.end ?? duration;
  const left = (start / duration) * 100;
  const right = 100 - (end / duration) * 100;
  const length = end - start;
  const approx = sizeBytes ? (sizeBytes * length) / duration : 0;

  function timeAt(clientX) {
    const rect = barRef.current.getBoundingClientRect();
    return Math.min(duration, Math.max(0, ((clientX - rect.left) / rect.width) * duration));
  }

  function move(event) {
    // Only while this handle holds the pointer (pressed and dragging).
    if (!event.currentTarget.hasPointerCapture?.(event.pointerId)) return;
    const drag = event.currentTarget.dataset.which;
    const t = timeAt(event.clientX);
    const min = Math.min(1, duration);
    if (drag === "start") {
      let next = Math.min(t, end - min);
      if (maxLength && end - next > maxLength) next = end - maxLength;
      onChange({ start: Math.max(0, next), end });
    } else {
      let next = Math.max(t, start + min);
      if (maxLength && next - start > maxLength) next = start + maxLength;
      onChange({ start, end: Math.min(duration, next) });
    }
  }

  const grab = (event) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const release = (event) => event.currentTarget.releasePointerCapture?.(event.pointerId);


  return (
    <div className="trimmer">
      <div className="trimmer__bar" ref={barRef}>
        <div className="trimmer__strip">
          {frames.length
            ? frames.map((frame, index) => (frame ? <img key={index} src={frame} alt="" draggable={false} /> : <span key={index} />))
            : Array.from({ length: 8 }, (_, index) => <span key={index} />)}
        </div>
        <div className="trimmer__shade" style={{ left: 0, width: `${left}%` }} />
        <div className="trimmer__shade" style={{ right: 0, width: `${right}%` }} />
        <div className="trimmer__window" style={{ left: `${left}%`, right: `${right}%` }}>
          <span className="trimmer__handle trimmer__handle--start" role="slider" aria-label="Start" aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.round(start)} data-which="start" onPointerDown={grab} onPointerMove={(event) => move(event)} onPointerUp={release} />
          <span className="trimmer__handle trimmer__handle--end" role="slider" aria-label="End" aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.round(end)} data-which="end" onPointerDown={grab} onPointerMove={(event) => move(event)} onPointerUp={release} />
        </div>
      </div>
      <p className="trimmer__info">
        {fmt(start)} – {fmt(end)} · {fmt(length)}
        {approx ? ` · ${approx >= 1048576 ? `${(approx / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(approx / 1024))} kB`}` : ""}
      </p>
    </div>
  );
}
