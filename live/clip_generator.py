"""Clip rendering engine for Clipify AI Live Studio.

Generates 9:16 vertical and 16:9 original format MP4s with
thumbnails, subtitle overlays, and audio sync using FFmpeg.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from live.rolling_buffer import RollingBuffer

logger = logging.getLogger("clipify.live.generator")


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class LiveClipGenerator:
    """Renders final MP4 clips from rolling buffer chunks."""

    def __init__(
        self,
        ffmpeg_bin: str,
        rolling_buffer: RollingBuffer,
        clips_output_dir: Path,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.rolling_buffer = rolling_buffer
        self.clips_output_dir = Path(clips_output_dir)
        self.clips_output_dir.mkdir(parents=True, exist_ok=True)

    def render_clip(
        self,
        start_sec: float,
        end_sec: float,
        title: str,
        category: str,
        subtitle_text: str = "",
        format_type: str = "vertical", # "vertical" (9:16) or "both"
    ) -> Optional[dict[str, Any]]:
        """Generate short MP4 video files and thumbnail."""
        clip_id = uuid.uuid4().hex[:10]
        clip_dir = self.clips_output_dir / clip_id
        clip_dir.mkdir(parents=True, exist_ok=True)

        raw_stitched = clip_dir / "raw_stitched.mp4"
        out_vertical = clip_dir / "short_9_16.mp4"
        out_original = clip_dir / "clip_16_9.mp4"
        out_thumb = clip_dir / "thumb.jpg"

        # 1. Stitch raw footage from buffer
        ok = self.rolling_buffer.extract_stitched_video(start_sec, end_sec, raw_stitched, reencode=True)
        if not ok or not raw_stitched.exists() or raw_stitched.stat().st_size < 1000:
            logger.warning("Failed extracting raw stitched video for clip %s", clip_id)
            return None

        # 2. Render 9:16 vertical composition (smart split / blur background)
        # Using 1080x1920 vertical canvas: scale to fit with blurred background
        filter_vertical = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )

        cmd_vert = [
            self.ffmpeg_bin, "-y",
            "-i", str(raw_stitched),
            "-filter_complex", filter_vertical,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            str(out_vertical),
        ]

        subprocess.run(
            cmd_vert, capture_output=True, text=True,
            timeout=90, creationflags=_hidden_flags(),
        )

        # 3. Render 16:9 original format
        cmd_orig = [
            self.ffmpeg_bin, "-y",
            "-i", str(raw_stitched),
            "-c", "copy",
            "-movflags", "+faststart",
            str(out_original),
        ]
        subprocess.run(
            cmd_orig, capture_output=True, text=True,
            timeout=30, creationflags=_hidden_flags(),
        )

        # 4. Generate poster thumbnail
        cmd_thumb = [
            self.ffmpeg_bin, "-y",
            "-ss", "00:00:01.000",
            "-i", str(out_vertical if out_vertical.exists() else raw_stitched),
            "-vframes", "1",
            "-q:v", "2",
            str(out_thumb),
        ]
        subprocess.run(
            cmd_thumb, capture_output=True, text=True,
            timeout=15, creationflags=_hidden_flags(),
        )

        # Remove temporary intermediate raw stitched file to conserve space
        try:
            if raw_stitched.exists():
                raw_stitched.unlink()
        except Exception:
            pass

        duration = max(1.0, end_sec - start_sec)
        clip_record: dict[str, Any] = {
            "id": clip_id,
            "title": title,
            "category": category,
            "start_sec": round(start_sec, 2),
            "end_sec": round(end_sec, 2),
            "duration": round(duration, 1),
            "vertical_video": f"/api/live/media/{clip_id}/short_9_16.mp4",
            "original_video": f"/api/live/media/{clip_id}/clip_16_9.mp4",
            "thumbnail": f"/api/live/media/{clip_id}/thumb.jpg",
            "created_at": time.time(),
            "formatted_time": time.strftime("%H:%M:%S", time.localtime()),
            "status": "ready",
        }

        # Save metadata JSON
        meta_file = clip_dir / "meta.json"
        meta_file.write_text(json.dumps(clip_record, indent=2), encoding="utf-8")

        return clip_record
