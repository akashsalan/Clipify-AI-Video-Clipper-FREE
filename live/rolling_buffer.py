"""Thread-safe rolling buffer manager for Clipify AI Live Studio.

Maintains a bounded window of video/audio chunks on disk and in memory,
automatically purging expired segments to avoid consuming unlimited disk space.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("clipify.live.buffer")


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass
class BufferChunk:
    index: int
    path: Path
    start_sec: float
    end_sec: float
    duration: float
    size_bytes: int


class RollingBuffer:
    """Bounded circular buffer on disk."""

    def __init__(
        self,
        buffer_dir: Path,
        ffmpeg_bin: str,
        max_duration_sec: int = 600, # 10 minutes default
        max_disk_mb: int = 2048,     # 2 GB max
    ):
        self.buffer_dir = Path(buffer_dir)
        self.ffmpeg_bin = ffmpeg_bin
        self.max_duration_sec = max_duration_sec
        self.max_disk_mb = max_disk_mb

        self.chunks: list[BufferChunk] = []
        self._lock = threading.Lock()
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

    def add_chunk(self, path: Path, index: int, stream_elapsed: float, duration: float = 5.0) -> BufferChunk:
        """Register a new completed segment into the rolling buffer."""
        start_sec = max(0.0, stream_elapsed - duration)
        end_sec = stream_elapsed
        size_bytes = path.stat().st_size if path.exists() else 0

        chunk = BufferChunk(
            index=index,
            path=path,
            start_sec=start_sec,
            end_sec=end_sec,
            duration=duration,
            size_bytes=size_bytes,
        )

        with self._lock:
            self.chunks.append(chunk)
            self._prune_locked()

        return chunk

    def _prune_locked(self) -> None:
        """Remove expired chunks that fall outside duration or disk limits."""
        if not self.chunks:
            return

        latest_end = self.chunks[-1].end_sec
        min_allowed_time = latest_end - self.max_duration_sec

        # Prune by time
        remaining: list[BufferChunk] = []
        for c in self.chunks:
            if c.end_sec < min_allowed_time:
                try:
                    if c.path.exists():
                        c.path.unlink()
                except Exception as e:
                    logger.debug("Failed removing expired chunk %s: %s", c.path.name, e)
            else:
                remaining.append(c)

        # Prune by disk space if needed
        total_bytes = sum(c.size_bytes for c in remaining)
        max_bytes = self.max_disk_mb * 1024 * 1024
        while total_bytes > max_bytes and len(remaining) > 2:
            oldest = remaining.pop(0)
            total_bytes -= oldest.size_bytes
            try:
                if oldest.path.exists():
                    oldest.path.unlink()
            except Exception:
                pass

        self.chunks = remaining

    def get_window_duration(self) -> float:
        """Return total duration currently held in buffer in seconds."""
        with self._lock:
            if not self.chunks:
                return 0.0
            return max(0.0, self.chunks[-1].end_sec - self.chunks[0].start_sec)

    def get_total_chunks(self) -> int:
        with self._lock:
            return len(self.chunks)

    def get_chunks_in_range(self, start_sec: float, end_sec: float) -> list[BufferChunk]:
        """Find all segments overlapping the requested [start_sec, end_sec] interval."""
        with self._lock:
            return [
                c for c in self.chunks
                if c.end_sec >= start_sec and c.start_sec <= end_sec and c.path.exists()
            ]

    def extract_stitched_video(
        self,
        start_sec: float,
        end_sec: float,
        output_path: Path,
        reencode: bool = True,
    ) -> bool:
        """Stitch chunks matching the given time range into a single MP4."""
        matching = self.get_chunks_in_range(start_sec, end_sec)
        if not matching:
            logger.warning("No buffer chunks match range %.1f to %.1f", start_sec, end_sec)
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create FFmpeg concat demuxer list
        concat_file = output_path.with_suffix(".concat.txt")
        try:
            lines = []
            for c in matching:
                p_str = str(c.path.resolve()).replace("\\", "/")
                lines.append(f"file '{p_str}'")
            concat_file.write_text("\n".join(lines), encoding="utf-8")

            # Offset within the first matching chunk
            first_chunk_start = matching[0].start_sec
            seek_offset = max(0.0, start_sec - first_chunk_start)
            clip_duration = max(1.0, end_sec - start_sec)

            if reencode:
                cmd = [
                    self.ffmpeg_bin, "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-ss", f"{seek_offset:.2f}",
                    "-t", f"{clip_duration:.2f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
            else:
                cmd = [
                    self.ffmpeg_bin, "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-ss", f"{seek_offset:.2f}",
                    "-t", f"{clip_duration:.2f}",
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ]

            res = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, creationflags=_hidden_flags(),
            )
            return res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024
        except Exception as e:
            logger.exception("Failed extracting stitched video: %s", e)
            return False
        finally:
            try:
                if concat_file.exists():
                    concat_file.unlink()
            except Exception:
                pass

    def extract_audio_wav(self, chunk_path: Path, output_wav: Path) -> bool:
        """Extract 16kHz mono PCM wav for Whisper speech recognition."""
        try:
            output_wav.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                self.ffmpeg_bin, "-y",
                "-i", str(chunk_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(output_wav),
            ]
            res = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, creationflags=_hidden_flags(),
            )
            return res.returncode == 0 and output_wav.exists() and output_wav.stat().st_size > 512
        except Exception as e:
            logger.debug("Failed extracting audio from %s: %s", chunk_path.name, e)
            return False

    def clear(self) -> None:
        """Purge all chunks and cleanup buffer directory."""
        with self._lock:
            for c in self.chunks:
                try:
                    if c.path.exists():
                        c.path.unlink()
                except Exception:
                    pass
            self.chunks.clear()
