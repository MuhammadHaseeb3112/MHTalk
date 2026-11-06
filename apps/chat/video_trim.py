"""
Cut a video to the part the user chose (start / end seconds) with ffmpeg.

The phone sends the whole file plus ``trim_start`` / ``trim_end``; we cut
without re-encoding (``-c copy``), so it takes a moment even on a small
server. If ffmpeg is missing or fails, the original video is kept.
"""

import logging
import os
import shutil
import subprocess
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

logger = logging.getLogger(__name__)


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def _seconds(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def trim_upload(upload, start, end):
    """Return a new uploaded file with only ``start``..``end`` (seconds)."""
    start, end = _seconds(start), _seconds(end)
    if upload is None or start is None or end is None or end - start < 0.5 or not ffmpeg_available():
        return upload
    name = os.path.basename(getattr(upload, "name", "") or "video.mp4")
    ext = os.path.splitext(name)[1].lower() or ".mp4"
    workdir = tempfile.mkdtemp(prefix="trim-")
    source = os.path.join(workdir, f"in{ext}")
    target = os.path.join(workdir, f"out{ext}")
    try:
        with open(source, "wb") as handle:
            for chunk in upload.chunks():
                handle.write(chunk)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", source, "-t", f"{end - start:.3f}",
            "-c", "copy", "-avoid_negative_ts", "make_zero",
        ]
        if ext in (".mp4", ".mov", ".m4v"):
            command += ["-movflags", "+faststart"]
        subprocess.run([*command, target], check=True, timeout=120, capture_output=True)
        if not os.path.getsize(target):
            return upload
        with open(target, "rb") as handle:
            data = handle.read()
        content_type = getattr(upload, "content_type", None) or "video/mp4"
        return SimpleUploadedFile(name, data, content_type=content_type)
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("Video trim failed, keeping the original: %s", error)
        if hasattr(upload, "seek"):
            upload.seek(0)
        return upload
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
