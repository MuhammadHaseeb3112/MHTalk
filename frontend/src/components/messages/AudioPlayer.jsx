import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Headphones, Mic, Pause, Play } from "lucide-react";
import { mediaUrl } from "../../api/client";
import { duration as formatDuration } from "../../utils/format";
import { Avatar } from "../common/ui";

const BAR_COUNT = 40;

/** Deterministic pseudo-waveform for audio without stored peaks. */
function fallbackWave(seed) {
  let value = Number(String(seed).replace(/\D/g, "").slice(-6)) || 7;
  return Array.from({ length: BAR_COUNT }, () => {
    value = (value * 9301 + 49297) % 233280;
    return 20 + Math.round((value / 233280) * 70);
  });
}

function resample(values) {
  if (!values?.length) return null;
  return Array.from({ length: BAR_COUNT }, (_, index) => {
    const source = values[Math.floor((index / BAR_COUNT) * values.length)];
    return Math.max(12, Math.min(100, Number(source) || 12));
  });
}

let activePlayer = null;

/**
 * WhatsApp-style audio bubble content.
 *  - voice notes: avatar with mic badge, waveform, speed toggle
 *  - audio files: headphones icon, file name, waveform
 */
function AudioPlayer({ src, seconds, waveform, isVoice, avatarSrc, avatarName, fileName, seed, outgoing, played }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [total, setTotal] = useState(Number(seconds) || 0);
  const [rate, setRate] = useState(1);
  const [error, setError] = useState(false);
  const [dragRatio, setDragRatio] = useState(null); // while dragging the knob
  const probingRef = useRef(false);
  const bars = useMemo(() => resample(waveform) || fallbackWave(seed || src), [waveform, seed, src]);
  const url = mediaUrl(src);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;
    const onTime = () => {
      if (!probingRef.current) setCurrent(audio.currentTime);
    };
    const onMeta = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) setTotal(audio.duration);
    };
    const onEnd = () => {
      setPlaying(false);
      setCurrent(0);
    };
    const onPause = () => setPlaying(false);
    const onPlay = () => setPlaying(true);
    const onError = () => setError(true);
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("durationchange", onMeta);
    audio.addEventListener("ended", onEnd);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("error", onError);
    return () => {
      audio.pause();
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("durationchange", onMeta);
      audio.removeEventListener("ended", onEnd);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("error", onError);
    };
  }, [url]);

  function toggle(event) {
    event.stopPropagation();
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      return;
    }
    if (activePlayer && activePlayer !== audio) activePlayer.pause();
    activePlayer = audio;
    audio.playbackRate = rate;
    audio.play().catch((err) => {
      // An interrupted play() (pause/seek right after) isn't a broken file.
      if (err?.name !== "AbortError") setError(true);
    });
  }

  // Voice notes recorded in the browser (MediaRecorder WebM) carry no
  // duration, so Chrome reports Infinity and ignores seeks. Jumping far past
  // the end makes it scan the file once and learn the real length.
  function ensureDuration(audio) {
    const known = () => (Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0);
    if (known()) return Promise.resolve(known());
    return new Promise((resolve) => {
      let timer;
      const finish = () => {
        window.clearTimeout(timer);
        audio.removeEventListener("durationchange", onChange);
        probingRef.current = false;
        const value = known();
        if (value) {
          audio.currentTime = 0;
          setTotal(value);
        }
        resolve(value || total);
      };
      const onChange = () => known() && finish();
      const probe = () => {
        probingRef.current = true;
        audio.currentTime = 1e101;
      };
      audio.addEventListener("durationchange", onChange);
      timer = window.setTimeout(finish, 4000);
      if (audio.readyState >= 1) probe();
      else {
        audio.addEventListener("loadedmetadata", probe, { once: true });
        audio.load();
      }
    });
  }

  async function seekTo(ratio) {
    const audio = audioRef.current;
    if (!audio) return;
    const length = await ensureDuration(audio);
    if (!length) return;
    audio.currentTime = Math.min(length - 0.05, Math.max(0, ratio * length));
    setCurrent(audio.currentTime);
  }

  // Tap or drag on the waveform to jump, like WhatsApp.
  function onWavePointerDown(event) {
    event.stopPropagation();
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const wave = event.currentTarget;
    const rect = wave.getBoundingClientRect();
    const ratioAt = (x) => Math.min(1, Math.max(0, (x - rect.left) / rect.width));
    wave.setPointerCapture?.(event.pointerId);
    setDragRatio(ratioAt(event.clientX));
    const onMove = (moveEvent) => setDragRatio(ratioAt(moveEvent.clientX));
    const onUp = (upEvent) => {
      wave.removeEventListener("pointermove", onMove);
      wave.removeEventListener("pointerup", onUp);
      wave.removeEventListener("pointercancel", onUp);
      setDragRatio(null);
      if (upEvent.type === "pointerup") seekTo(ratioAt(upEvent.clientX));
    };
    wave.addEventListener("pointermove", onMove);
    wave.addEventListener("pointerup", onUp);
    wave.addEventListener("pointercancel", onUp);
  }

  function onWaveKeyDown(event) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    if (!total) return;
    const step = event.key === "ArrowRight" ? 5 : -5;
    seekTo((current + step) / total);
  }

  function cycleRate(event) {
    event.stopPropagation();
    const next = rate === 1 ? 1.5 : rate === 1.5 ? 2 : 1;
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  }

  const progress = dragRatio ?? (total ? Math.min(1, current / total) : 0);

  return (
    <div className={`audio ${isVoice ? "audio--voice" : "audio--file"} ${outgoing ? "is-out" : ""}`}>
      <audio ref={audioRef} src={url} preload="metadata" />
      {isVoice && !playing && current === 0 ? (
        <div className="audio__avatar">
          <Avatar src={avatarSrc} name={avatarName} size={46} />
          <span className={`audio__mic ${played ? "is-played" : ""}`}><Mic size={13} /></span>
        </div>
      ) : isVoice ? (
        <button type="button" className="audio__rate" onClick={cycleRate} aria-label="Playback speed">
          {rate}×
        </button>
      ) : (
        <div className="audio__file-icon"><Headphones size={22} /></div>
      )}
      <button type="button" className="audio__play" onClick={toggle} aria-label={playing ? "Pause" : "Play"} disabled={error}>
        {playing ? <Pause size={24} fill="currentColor" /> : <Play size={24} fill="currentColor" />}
      </button>
      <div className="audio__track">
        {fileName ? <span className="audio__name">{fileName}</span> : null}
        <div
          className="audio__wave"
          onPointerDown={onWavePointerDown}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={onWaveKeyDown}
          role="slider"
          aria-label="Seek"
          aria-valuemin={0}
          aria-valuemax={Math.round(total)}
          aria-valuenow={Math.round(current)}
          tabIndex={0}
        >
          {bars.map((height, index) => (
            <span key={index} className={index / bars.length < progress ? "is-played" : ""} style={{ height: `${height}%` }} />
          ))}
          <span className="audio__knob" style={{ left: `${progress * 100}%` }} />
        </div>
        <span className="audio__time">{error ? "Audio unavailable" : formatDuration(playing || current ? current : total)}</span>
      </div>
    </div>
  );
}

export default memo(AudioPlayer);
