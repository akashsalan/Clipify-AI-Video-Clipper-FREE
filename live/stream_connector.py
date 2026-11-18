"""Live stream ingestion connector for Clipify AI Live Studio.

Supports YouTube Live, TikTok Live, and OBS Studio local RTMP ingestion.
Continuous capture writes bounded video/audio segments into the rolling buffer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("clipify.live.connector")

# Common regex patterns for live sources
YOUTUBE_LIVE_REGEX = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com/(watch\?v=|live/|@[\w.-]+/live|c/[\w.-]+/live)|youtu\.be/)([\w-]{6,12})",
    re.IGNORECASE,
)
TIKTOK_LIVE_REGEX = re.compile(
    r"^(https?://)?(www\.)?tiktok\.com/@([\w.-]+)(/live)?",
    re.IGNORECASE,
)


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class StreamConnector:
    """Manages the ingestion subprocess and stream health."""

    def __init__(
        self,
        source_type: str,
        source_url: str,
        buffer_dir: Path,
        ffmpeg_bin: str,
        python_bin: Optional[str] = None,
        segment_duration: int = 5,
        on_segment_ready: Optional[Callable[[Path, int, float], None]] = None,
        on_status_change: Optional[Callable[[str, str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.source_type = source_type.lower().strip()
        self.source_url = source_url.strip()
        self.buffer_dir = Path(buffer_dir)
        self.ffmpeg_bin = ffmpeg_bin
        self.python_bin = python_bin or "python"
        self.segment_duration = max(3, min(15, segment_duration))
        self.on_segment_ready = on_segment_ready
        self.on_status_change = on_status_change
        self.on_error = on_error

        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stream_metadata: dict[str, Any] = {
            "title": "Live Stream",
            "author": "",
            "resolution": "1080p",
            "fps": 30,
            "is_live": True,
            "source_type": self.source_type,
        }
        self.connected_at: Optional[float] = None
        self.segments_recorded = 0
        self._stop_event = threading.Event()

    def validate(self) -> tuple[bool, str]:
        """Validate input parameters for the chosen source."""
        if self.source_type == "youtube":
            if not self.source_url:
                return False, "Please enter a valid YouTube Live URL."
            if not YOUTUBE_LIVE_REGEX.search(self.source_url):
                # Loose check for channel URLs
                if "youtube.com" not in self.source_url:
                    return False, "Not a recognized YouTube live stream link."
            return True, ""
        elif self.source_type == "tiktok":
            if not self.source_url:
                return False, "Please enter a TikTok live URL or username."
            return True, ""
        elif self.source_type == "obs":
            # OBS uses local socket ingestion; source_url is optional (defaults to 127.0.0.1:1935)
            return True, ""
        return False, f"Unsupported source type: {self.source_type}"

    def probe_metadata(self) -> dict[str, Any]:
        """Probe stream details prior to / during capture."""
        if self.source_type == "youtube":
            try:
                cmd = [
                    self.python_bin, "-m", "yt_dlp",
                    "--dump-json", "--no-warnings", "--no-playlist",
                    "--socket-timeout", "10",
                    self.source_url,
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=15, creationflags=_hidden_flags(),
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout.strip().splitlines()[0])
                    self.stream_metadata["title"] = data.get("title", "YouTube Live Stream")
                    self.stream_metadata["author"] = data.get("uploader", "")
                    self.stream_metadata["is_live"] = bool(data.get("is_live", True))
                    if data.get("width") and data.get("height"):
                        self.stream_metadata["resolution"] = f"{data['width']}x{data['height']}"
                    if data.get("fps"):
                        self.stream_metadata["fps"] = data["fps"]
            except Exception as e:
                logger.warning("yt-dlp probe failed or timed out: %s", e)
                self.stream_metadata["title"] = "YouTube Live Stream"

        elif self.source_type == "obs":
            self.stream_metadata["title"] = "OBS Studio Ingestion"
            self.stream_metadata["author"] = "Local Broadcast"
            self.stream_metadata["resolution"] = "1920x1080"
            self.stream_metadata["fps"] = 60

        elif self.source_type == "tiktok":
            self.stream_metadata["title"] = f"TikTok Live: {self.source_url}"
            self.stream_metadata["author"] = self.source_url

        return self.stream_metadata

    def start(self) -> None:
        """Start capturing the stream into rolling buffer segments."""
        if self.is_running:
            return

        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self.is_running = True
        self.connected_at = time.time()

        if self.on_status_change:
            self.on_status_change("connecting", "Initializing live stream capture...")

        self.monitor_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self) -> None:
        """Gracefully stop stream ingestion."""
        self.is_running = False
        self._stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        if self.on_status_change:
            self.on_status_change("disconnected", "Live stream capture stopped.")

    def _build_ffmpeg_args(self) -> list[str]:
        """Construct the FFmpeg command for the configured source."""
        out_pattern = str(self.buffer_dir / "chunk_%05d.mp4")

        # Base segment options: h264 fast, aac 160k, rolling segment files
        common_output = [
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "16000", "-ac", "1",
            "-f", "segment",
            "-segment_time", str(self.segment_duration),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-movflags", "+faststart+frag_keyframe+empty_moov",
            "-y", out_pattern,
        ]

        if self.source_type == "obs":
            # Listen on RTMP or fallback HTTP MPEG-TS
            rtmp_url = self.source_url if self.source_url.startswith("rtmp://") else "rtmp://127.0.0.1:1935/live/stream"
            return [
                self.ffmpeg_bin, "-listen", "1", "-i", rtmp_url,
                *common_output,
            ]

        elif self.source_type == "youtube":
            # Ingest through yt-dlp piped into ffmpeg or direct stream URL
            # yt-dlp -o - <url> | ffmpeg -i pipe:0 ...
            return [
                self.ffmpeg_bin,
                "-re",
                "-i", self.source_url,
                *common_output,
            ]

        else: # tiktok or generic url
            return [
                self.ffmpeg_bin,
                "-re",
                "-i", self.source_url,
                *common_output,
            ]

    def _capture_loop(self) -> None:
        """Background thread executing capture with automatic recovery."""
        retry_delay = 2

        while not self._stop_event.is_set():
            try:
                # If YouTube, we can resolve the live HLS stream URL using yt-dlp first
                target_url = self.source_url
                if self.source_type == "youtube":
                    if self.on_status_change:
                        self.on_status_change("connecting", "Resolving live stream feed...")
                    try:
                        res = subprocess.run(
                            [
                                self.python_bin, "-m", "yt_dlp",
                                "-g", "--no-warnings", "-f", "best[height<=1080]/best",
                                self.source_url,
                            ],
                            capture_output=True, text=True, timeout=20,
                            creationflags=_hidden_flags(),
                        )
                        if res.returncode == 0 and res.stdout.strip():
                            target_url = res.stdout.strip().splitlines()[0]
                            logger.info("Resolved live stream URL: %s...", target_url[:60])
                    except Exception as e:
                        logger.warning("Failed resolving live stream with yt-dlp: %s", e)

                out_pattern = str(self.buffer_dir / "chunk_%05d.mp4")
                if self.source_type == "obs":
                    listen_url = self.source_url if self.source_url.startswith("rtmp://") else "rtmp://127.0.0.1:1935/live/stream"
                    cmd = [
                        self.ffmpeg_bin, "-listen", "1", "-i", listen_url,
                        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "16000",
                        "-f", "segment", "-segment_time", str(self.segment_duration),
                        "-segment_format", "mp4", "-reset_timestamps", "1",
                        "-movflags", "+faststart+frag_keyframe+empty_moov",
                        "-y", out_pattern,
                    ]
                else:
                    cmd = [
                        self.ffmpeg_bin,
                        "-reconnect", "1", "-reconnect_at_eof", "1",
                        "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                        "-i", target_url,
                        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "16000",
                        "-f", "segment", "-segment_time", str(self.segment_duration),
                        "-segment_format", "mp4", "-reset_timestamps", "1",
                        "-movflags", "+faststart+frag_keyframe+empty_moov",
                        "-y", out_pattern,
                    ]

                logger.info("Starting live capture subprocess: %s", " ".join(cmd[:5]))
                if self.on_status_change:
                    self.on_status_change("live", f"Connected to {self.source_type.upper()} Live Stream")

                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    creationflags=_hidden_flags(),
                )

                # Monitor output directory for newly created segments
                known_chunks: set[str] = set()
                while not self._stop_event.is_set():
                    poll_res = self.process.poll()
                    if poll_res is not None:
                        logger.warning("Capture process exited with code %d", poll_res)
                        break

                    # Check for completed chunks (a chunk is complete when the next one appears or size stabilizes)
                    files = sorted(self.buffer_dir.glob("chunk_*.mp4"))
                    if len(files) >= 2:
                        for chunk in files[:-1]: # All except currently writing last chunk
                            if chunk.name not in known_chunks and chunk.stat().st_size > 1024:
                                known_chunks.add(chunk.name)
                                self.segments_recorded += 1
                                elapsed = (time.time() - self.connected_at) if self.connected_at else 0
                                if self.on_segment_ready:
                                    try:
                                        self.on_segment_ready(chunk, self.segments_recorded, elapsed)
                                    except Exception as exc:
                                        logger.exception("Error in on_segment_ready: %s", exc)

                    time.sleep(1.0)

            except Exception as e:
                logger.exception("Capture loop error: %s", e)
                if self.on_error:
                    self.on_error(str(e))

            if self._stop_event.is_set():
                break

            if self.on_status_change:
                self.on_status_change("reconnecting", f"Stream disconnected. Reconnecting in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(15, retry_delay * 1.5)

        self.is_running = False
