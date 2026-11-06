import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Circle, Image as ImageIcon, RefreshCcw, SwitchCamera, Video, X } from "lucide-react";
import { duration as formatDuration } from "../../utils/format";
import { IconButton, Spinner } from "../common/ui";

/**
 * Camera capture: live preview, take a photo or record a short video.
 * The captured File is handed to the media composer for preview/caption.
 */
export default function CameraCapture({ onCapture, onClose, onGallery }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const [status, setStatus] = useState("starting"); // starting | ready | recording | error
  const [error, setError] = useState("");
  const [mode, setMode] = useState("photo");
  const [facing, setFacing] = useState("user");
  const [seconds, setSeconds] = useState(0);
  const [attempt, setAttempt] = useState(0);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      setStatus("starting");
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Camera access needs a supported browser over HTTPS (or localhost).");
        setStatus("error");
        return;
      }
      try {
        stopStream();
        // Ask for exactly the front or back camera first (phones), then fall
        // back to "whichever is closest" for laptops with one camera.
        const size = { width: { ideal: 1280 }, height: { ideal: 720 } };
        let stream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { exact: facing }, ...size }, audio: true });
        } catch (exactError) {
          if (exactError?.name === "NotAllowedError") throw exactError;
          stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: facing, ...size }, audio: true });
        }
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setStatus("ready");
      } catch (err) {
        setError(err?.name === "NotAllowedError" ? "Camera permission was denied. Allow camera access in your browser settings and try again." : "No camera was found or it is in use by another app.");
        setStatus("error");
      }
    }
    start();
    return () => {
      cancelled = true;
    };
  }, [facing, attempt, stopStream]);

  useEffect(() => () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    stopStream();
  }, [stopStream]);

  useEffect(() => {
    if (status !== "recording") return undefined;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  function flip() {
    setFacing((value) => (value === "user" ? "environment" : "user"));
  }

  function takePhoto() {
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (facing === "user") {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      stopStream();
      onCapture(new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  }

  function toggleRecording() {
    if (status === "recording") {
      recorderRef.current?.stop();
      return;
    }
    if (typeof MediaRecorder === "undefined" || !streamRef.current) {
      setError("Video recording isn't supported in this browser.");
      return;
    }
    const type = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"].find((item) => MediaRecorder.isTypeSupported?.(item)) || "";
    const recorder = new MediaRecorder(streamRef.current, type ? { mimeType: type } : undefined);
    recorderRef.current = recorder;
    chunksRef.current = [];
    recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "video/webm" });
      stopStream();
      if (blob.size) onCapture(new File([blob], `video-${Date.now()}.${blob.type.includes("mp4") ? "mp4" : "webm"}`, { type: blob.type }));
      else onClose();
    };
    recorder.start(500);
    setSeconds(0);
    setStatus("recording");
  }

  return (
    <div className="camera" role="dialog" aria-label="Camera">
      <div className="camera__top">
        <IconButton icon={X} label="Close camera" onClick={() => { stopStream(); onClose(); }} />
        <span>{status === "recording" ? <><span className="recorder__dot" /> {formatDuration(seconds)}</> : "Take photo"}</span>
        <span className="camera__spacer" />
      </div>
      <div className="camera__view" onDoubleClick={() => status !== "recording" && flip()}>
        {status === "starting" ? <Spinner size={32} /> : null}
        {status === "error" ? (
          <div className="camera__error">
            <Camera size={42} />
            <p>{error}</p>
            <button type="button" className="btn btn--ghost" onClick={() => setAttempt((value) => value + 1)}>
              <RefreshCcw size={16} /> Try again
            </button>
          </div>
        ) : null}
        <video ref={videoRef} playsInline muted className={facing === "user" ? "is-mirrored" : ""} style={{ visibility: status === "ready" || status === "recording" ? "visible" : "hidden" }} />
      </div>
      <div className="camera__controls">
        <div className="camera__modes">
          <button type="button" className={`chip ${mode === "photo" ? "is-active" : ""}`} onClick={() => setMode("photo")} disabled={status === "recording"}>
            <Camera size={16} /> Photo
          </button>
          <button type="button" className={`chip ${mode === "video" ? "is-active" : ""}`} onClick={() => setMode("video")} disabled={status === "recording"}>
            <Video size={16} /> Video
          </button>
        </div>
        <div className="camera__row">
          {onGallery ? (
            <button type="button" className="camera__round" aria-label="Gallery" disabled={status === "recording"} onClick={() => { stopStream(); onGallery(); }}>
              <ImageIcon size={24} />
            </button>
          ) : <span className="camera__round camera__round--blank" />}
          <button
            type="button"
            className={`shutter ${mode === "video" ? "shutter--video" : ""} ${status === "recording" ? "is-recording" : ""}`}
            onClick={mode === "photo" ? takePhoto : toggleRecording}
            disabled={status !== "ready" && status !== "recording"}
            aria-label={mode === "photo" ? "Take photo" : status === "recording" ? "Stop recording" : "Start recording"}
          >
            <Circle size={58} />
          </button>
          <button type="button" className="camera__round" aria-label="Switch camera (front / back)" onClick={flip} disabled={status === "recording"}>
            <SwitchCamera size={24} />
          </button>
        </div>
      </div>
    </div>
  );
}
