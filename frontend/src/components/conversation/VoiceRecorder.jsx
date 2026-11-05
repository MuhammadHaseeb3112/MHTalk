import { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ChevronLeft, ChevronUp, Lock, Mic, Pause, Send, Trash2 } from "lucide-react";
import { duration as formatDuration } from "../../utils/format";
import { toast } from "../../services/toast";
import AudioPlayer from "../messages/AudioPlayer";
import { ViewOnceIcon } from "../messages/FeatureCards";

const MAX_SECONDS = 600;

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return null;
  const candidates = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((type) => MediaRecorder.isTypeSupported?.(type)) || "";
}

const MIN_HOLD_MS = 700; // shorter holds are discarded, like WhatsApp

/**
 * Voice note recorder (MediaRecorder), laid out like WhatsApp: record, pause
 * to listen back to what's recorded so far, resume with the mic, delete or
 * send, optionally as "view once". Collects waveform peaks for the bubble.
 *
 * Press-and-hold mode (`hold`): the Composer tracks the finger/mouse and
 * calls ref.current.release() (send) or .cancel(); sliding up locks
 * the recording, which then shows the full recorder.
 */
export default function VoiceRecorder({ onCancel, onSend, hold = false, gesture = null, ref = null }) {
  const [phase, setPhase] = useState("starting"); // starting | recording | paused | preview (10-minute limit reached)
  const [viewOnce, setViewOnce] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState([]);
  const [preview, setPreview] = useState(null); // { blob, url }
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const peaksRef = useRef([]);
  const audioCtxRef = useRef(null);
  const rafRef = useRef(null);
  const timerRef = useRef(null);
  const discardRef = useRef(false);
  const startedAtRef = useRef(0);

  const cleanup = useCallback(() => {
    window.cancelAnimationFrame(rafRef.current);
    window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    discardRef.current = false; // React StrictMode runs this effect twice in development
    async function start() {
      const mimeType = pickMimeType();
      if (mimeType === null || !navigator.mediaDevices?.getUserMedia) {
        toast.error("Voice recording isn't supported in this browser.");
        onCancel();
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        recorderRef.current = recorder;
        chunksRef.current = [];
        recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
        recorder.onstop = () => {
          cleanup();
          if (discardRef.current) return;
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || "audio/webm" });
          if (!blob.size) {
            toast.error("Nothing was recorded. Check your microphone.");
            onCancel();
            return;
          }
          setPreview({ blob, url: URL.createObjectURL(blob), peaks: peaksRef.current.slice() });
          setPhase("preview");
        };
        recorder.start(250);
        startedAtRef.current = performance.now();
        setPhase("recording");

        // Live level meter + waveform peaks.
        const context = new (window.AudioContext || window.webkitAudioContext)();
        audioCtxRef.current = context;
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        context.createMediaStreamSource(stream).connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        let last = 0;
        const tick = (time) => {
          analyser.getByteTimeDomainData(data);
          let peak = 0;
          for (let i = 0; i < data.length; i += 1) peak = Math.max(peak, Math.abs(data[i] - 128));
          const level = Math.min(100, Math.round((peak / 128) * 160) + 8);
          if (time - last > 100 && recorderRef.current?.state === "recording") {
            last = time;
            peaksRef.current.push(level);
            setLevels((current) => [...current.slice(-59), level]);
          }
          rafRef.current = window.requestAnimationFrame(tick);
        };
        rafRef.current = window.requestAnimationFrame(tick);

        timerRef.current = window.setInterval(() => {
          if (recorderRef.current?.state !== "recording") return;
          setSeconds((value) => {
            if (value + 1 >= MAX_SECONDS) recorderRef.current?.stop();
            return value + 1;
          });
        }, 1000);
      } catch (error) {
        toast.error(error?.name === "NotAllowedError" ? "Allow microphone access to record voice messages." : "Couldn't access the microphone.");
        onCancel();
      }
    }
    start();
    return () => {
      cancelled = true;
      discardRef.current = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
      cleanup();
    };
    // run once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => preview?.url && URL.revokeObjectURL(preview.url), [preview]);

  // Pausing lets you listen to the recording so far (like WhatsApp); the
  // red mic resumes recording into the same voice message.
  function pause() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "recording") return;
    recorder.addEventListener(
      "dataavailable",
      () => {
        if (recorderRef.current?.state !== "paused") return;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setPreview({ blob, url: URL.createObjectURL(blob), peaks: peaksRef.current.slice() });
      },
      { once: true },
    );
    recorder.pause();
    recorder.requestData();
    setPhase("paused");
  }

  function resume() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "paused") return;
    setPreview(null);
    recorder.resume();
    setPhase("recording");
  }

  function discard() {
    discardRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    cleanup();
    onCancel();
  }

  function send() {
    if (phase === "preview" && preview) {
      onSend(preview.blob, Math.max(1, seconds), preview.peaks, viewOnce);
      return;
    }
    // Send directly while recording: stop, then send once the blob is ready.
    const recorder = recorderRef.current;
    if (!recorder) return;
    recorder.addEventListener(
      "stop",
      () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (blob.size) onSend(blob, Math.max(1, seconds), peaksRef.current, viewOnce);
      },
      { once: true },
    );
    discardRef.current = true;
    recorder.stop();
  }

  // Finger/mouse released while holding: send, unless it was too short.
  function release() {
    const recorder = recorderRef.current;
    const heldFor = startedAtRef.current ? performance.now() - startedAtRef.current : 0;
    if (!recorder || recorder.state === "inactive" || heldFor < MIN_HOLD_MS) {
      discard();
      toast("Hold to record, release to send");
      return;
    }
    send();
  }

  useImperativeHandle(ref, () => ({ release, cancel: discard }));

  if (hold) {
    const dx = gesture?.dx || 0;
    const dy = gesture?.dy || 0;
    return (
      <div className="recorder recorder--hold" role="group" aria-label="Recording voice message. Release to send, slide left to cancel, slide up to lock.">
        <span className="recorder__dot" />
        <span className="recorder__time">{formatDuration(seconds)}</span>
        <span className="recorder__slide" style={{ transform: `translateX(${dx * 0.6}px)`, opacity: Math.max(0.15, 1 + dx / 130) }}>
          <ChevronLeft size={18} /> Slide to cancel
        </span>
        <span className="recorder__lock" style={{ transform: `translateY(${Math.max(dy, -70) * 0.6}px)` }} aria-hidden>
          <Lock size={16} />
          <ChevronUp size={16} />
        </span>
        <span className="recorder__holdmic" aria-hidden>
          <Mic size={24} />
        </span>
      </div>
    );
  }

  return (
    <div className="recorder" role="group" aria-label="Voice message recorder">
      <button type="button" className="icon-btn" onClick={discard} aria-label="Delete recording">
        <Trash2 size={22} />
      </button>
      {(phase === "preview" || phase === "paused") && preview ? (
        <div className="recorder__preview">
          <AudioPlayer src={preview.url} seconds={seconds} waveform={preview.peaks} isVoice={false} seed="preview" outgoing />
        </div>
      ) : (
        <>
          <span className={`recorder__dot ${phase === "paused" ? "is-paused" : ""}`} />
          <span className="recorder__time">{formatDuration(seconds)}</span>
          <div className="recorder__wave" aria-hidden>
            {levels.map((level, index) => (
              <span key={index} style={{ height: `${level}%` }} />
            ))}
          </div>
        </>
      )}
      {phase === "paused" ? (
        <button type="button" className="icon-btn recorder__resume" onClick={resume} aria-label="Resume recording" data-tooltip="Resume">
          <Mic size={22} />
        </button>
      ) : phase !== "preview" ? (
        <button type="button" className="icon-btn" onClick={pause} aria-label="Pause recording" data-tooltip="Pause" disabled={phase === "starting"}>
          <Pause size={22} />
        </button>
      ) : null}
      <button
        type="button"
        className={`icon-btn view-once-toggle ${viewOnce ? "is-on" : ""}`}
        aria-pressed={viewOnce}
        aria-label={viewOnce ? "View once on" : "View once off"}
        data-tooltip="View once"
        onClick={() => {
          setViewOnce((value) => !value);
          toast(viewOnce ? "View once turned off" : "Voice message set to view once");
        }}
      >
        <ViewOnceIcon size={22} opened={false} />
      </button>
      <button type="button" className="send-btn" onClick={send} aria-label="Send voice message" disabled={phase === "starting"}>
        <Send size={22} />
      </button>
    </div>
  );
}
