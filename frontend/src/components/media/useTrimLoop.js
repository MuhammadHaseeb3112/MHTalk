import { useEffect } from "react";

/** Keep a <video> playing inside the chosen part. */
export function useTrimLoop(videoRef, trim) {
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !trim) return undefined;
    if (video.currentTime < trim.start || video.currentTime > trim.end) video.currentTime = trim.start;
    const onTime = () => {
      if (video.currentTime >= trim.end - 0.05) {
        video.currentTime = trim.start;
        if (!video.paused) video.play().catch(() => {});
      }
    };
    video.addEventListener("timeupdate", onTime);
    return () => video.removeEventListener("timeupdate", onTime);
  }, [videoRef, trim]);
}
