"""Coordinator singleton for Clipify AI Live Studio.

Orchestrates live ingestion, rolling buffers, transcription,
highlight analysis, clip generation, and status telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

from live.clip_generator import LiveClipGenerator
from live.highlight_detector import HighlightDetector, HighlightCandidate
from live.rolling_buffer import RollingBuffer
from live.stream_connector import StreamConnector
from live.transcriber import LiveTranscriber, LiveTranscriptSegment

logger = logging.getLogger("clipify.live.manager")


class LiveStudioManager:
    """Coordinates active Live Studio session."""

    def __init__(self, data_dir: Path, ffmpeg_bin: str, python_bin: str):
        self.data_dir = Path(data_dir)
        self.ffmpeg_bin = ffmpeg_bin
        self.python_bin = python_bin

        self.live_root = self.data_dir / "live_studio"
        self.buffer_dir = self.live_root / "buffer"
        self.clips_dir = self.live_root / "clips"
        self.live_root.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

        self.session_active = False
        self.status = "idle"  # "idle", "connecting", "live", "reconnecting", "disconnected"
        self.status_detail = "Ready to connect to live stream"

        self.source_type = "youtube"
        self.source_url = ""
        self.auto_clip_enabled = True
        self.sensitivity = 5
        self.buffer_minutes = 10
        self.stream_metadata: dict[str, Any] = {}
        self.session_start_time: Optional[float] = None

        self.connector: Optional[StreamConnector] = None
        self.buffer: Optional[RollingBuffer] = None
        self.transcriber: Optional[LiveTranscriber] = None
        self.detector: Optional[HighlightDetector] = None
        self.generator: Optional[LiveClipGenerator] = None

        self.live_events: list[dict[str, Any]] = []
        self.recent_transcripts: list[dict[str, Any]] = []
        self.clips: list[dict[str, Any]] = []

        self._lock = threading.Lock()
        self._load_saved_clips()

    def _load_saved_clips(self) -> None:
        """Load any existing clips from previous sessions on disk."""
        self.clips.clear()
        if not self.clips_dir.exists():
            return
        for clip_folder in self.clips_dir.iterdir():
            if clip_folder.is_dir():
                meta_json = clip_folder / "meta.json"
                if meta_json.exists():
                    try:
                        data = json.loads(meta_json.read_text(encoding="utf-8"))
                        self.clips.append(data)
                    except Exception:
                        pass
        self.clips.sort(key=lambda c: c.get("created_at", 0), reverse=True)

    def get_obs_config(self) -> dict[str, str]:
        """Return OBS Studio connection parameters."""
        return {
            "server": "rtmp://127.0.0.1:1935/live",
            "stream_key": "stream",
            "instructions": "In OBS Studio, open Settings -> Stream -> Service: Custom -> Server: rtmp://127.0.0.1:1935/live -> Stream Key: stream -> Click Start Streaming.",
        }

    def start_session(
        self,
        source_type: str,
        source_url: str,
        auto_clip: bool = True,
        sensitivity: int = 5,
        buffer_minutes: int = 10,
        model_name: str = "qwen2.5:3b",
    ) -> tuple[bool, str]:
        """Initialize and start a live studio monitoring session."""
        with self._lock:
            if self.session_active:
                return False, "A live session is already running. Stop it before starting a new one."

            self.source_type = source_type.lower().strip()
            self.source_url = source_url.strip()
            self.auto_clip_enabled = auto_clip
            self.sensitivity = max(1, min(10, sensitivity))
            self.buffer_minutes = max(3, min(30, buffer_minutes))

            # Initialize components
            self.buffer = RollingBuffer(
                buffer_dir=self.buffer_dir,
                ffmpeg_bin=self.ffmpeg_bin,
                max_duration_sec=self.buffer_minutes * 60,
            )
            self.buffer.clear()

            self.generator = LiveClipGenerator(
                ffmpeg_bin=self.ffmpeg_bin,
                rolling_buffer=self.buffer,
                clips_output_dir=self.clips_dir,
            )

            self.detector = HighlightDetector(
                model_name=model_name,
                sensitivity=self.sensitivity,
            )

            self.transcriber = LiveTranscriber(
                python_bin=self.python_bin,
                ffmpeg_bin=self.ffmpeg_bin,
                on_segment=self._on_transcript_segment,
            )
            self.transcriber.start()

            self.connector = StreamConnector(
                source_type=self.source_type,
                source_url=self.source_url,
                buffer_dir=self.buffer_dir,
                ffmpeg_bin=self.ffmpeg_bin,
                python_bin=self.python_bin,
                on_segment_ready=self._on_segment_ready,
                on_status_change=self._on_status_change,
                on_error=self._on_connector_error,
            )

            valid, err = self.connector.validate()
            if not valid:
                self.transcriber.stop()
                return False, err

            # Probe initial stream metadata
            threading.Thread(target=self._probe_and_start, daemon=True).start()

            self.session_active = True
            self.session_start_time = time.time()
            self.status = "connecting"
            self.status_detail = f"Connecting to {self.source_type.upper()} live stream..."
            self.recent_transcripts.clear()
            self._emit_event("session_started", {"source_type": self.source_type})

            return True, "Connecting to live stream"

    def _probe_and_start(self) -> None:
        """Background probe and stream launch."""
        if self.connector:
            meta = self.connector.probe_metadata()
            self.stream_metadata = meta
            self.connector.start()

    def stop_session(self) -> None:
        """Stop capture and transcription cleanly."""
        with self._lock:
            if not self.session_active:
                return

            self.session_active = False
            self.status = "idle"
            self.status_detail = "Live Studio session ended."

            if self.connector:
                self.connector.stop()
                self.connector = None

            if self.transcriber:
                self.transcriber.stop()
                self.transcriber = None

            if self.buffer:
                self.buffer.clear()

            self._emit_event("session_stopped", {})

    def _on_status_change(self, status: str, detail: str) -> None:
        self.status = status
        self.status_detail = detail
        self._emit_event("status_change", {"status": status, "detail": detail})

    def _on_connector_error(self, err_msg: str) -> None:
        self.status_detail = f"Stream error: {err_msg}"
        self._emit_event("stream_error", {"error": err_msg})

    def _on_segment_ready(self, chunk_path: Path, index: int, stream_elapsed: float) -> None:
        """Callback when a new 5-second chunk is saved by FFmpeg."""
        if not self.buffer or not self.transcriber:
            return

        chunk = self.buffer.add_chunk(chunk_path, index, stream_elapsed)

        # Extract WAV audio for transcription
        wav_path = chunk_path.with_suffix(".wav")
        if self.buffer.extract_audio_wav(chunk_path, wav_path):
            self.transcriber.enqueue_chunk(wav_path, chunk.start_sec, chunk.duration)

    def _on_transcript_segment(self, segment: LiveTranscriptSegment) -> None:
        """Callback when speech is transcribed."""
        seg_dict = {
            "start": round(segment.start_sec, 2),
            "end": round(segment.end_sec, 2),
            "text": segment.text,
            "speaker": segment.speaker,
        }
        self.recent_transcripts.append(seg_dict)
        if len(self.recent_transcripts) > 100:
            self.recent_transcripts.pop(0)

        self._emit_event("transcript", seg_dict)

        # Check for highlights if auto-clip is enabled
        if self.auto_clip_enabled and self.detector and self.generator:
            recent_segments = self.transcriber.get_recent_transcripts(last_n_seconds=45.0) if self.transcriber else []
            candidate = self.detector.evaluate(recent_segments)
            if candidate:
                threading.Thread(
                    target=self._trigger_clip_generation,
                    args=(candidate,),
                    daemon=True,
                ).start()

    def _trigger_clip_generation(self, candidate: HighlightCandidate) -> None:
        """Renders an auto-detected highlight into MP4 clips."""
        if not self.generator:
            return

        self._emit_event("highlight_detected", {
            "title": candidate.title,
            "category": candidate.category,
            "score": candidate.score,
        })

        clip_data = self.generator.render_clip(
            start_sec=candidate.start_sec,
            end_sec=candidate.end_sec,
            title=candidate.title,
            category=candidate.category,
            subtitle_text=candidate.transcript_snippet,
        )

        if clip_data:
            with self._lock:
                self.clips.insert(0, clip_data)
            self._emit_event("new_clip", clip_data)

    def instant_clip(self, duration_sec: int = 30) -> Optional[dict[str, Any]]:
        """User manual trigger: capture the last N seconds into a Short."""
        with self._lock:
            if not self.session_active or not self.buffer or not self.generator:
                return None

            duration_sec = max(10, min(90, duration_sec))
            current_time = (time.time() - self.session_start_time) if self.session_start_time else 0.0
            start_sec = max(0.0, current_time - duration_sec)
            end_sec = current_time

            title = f"Live Highlight #{len(self.clips) + 1}"
            category = "High-energy moments"

            # Check recent transcript for title inspiration
            if self.recent_transcripts:
                last_txt = self.recent_transcripts[-1].get("text", "")
                if last_txt:
                    words = last_txt.split()[:5]
                    title = " ".join(words).title() + "!"

            clip_data = self.generator.render_clip(
                start_sec=start_sec,
                end_sec=end_sec,
                title=title,
                category=category,
            )

            if clip_data:
                self.clips.insert(0, clip_data)
                self._emit_event("new_clip", clip_data)
                return clip_data

            return None

    def delete_clip(self, clip_id: str) -> bool:
        """Delete a generated clip from memory and disk."""
        with self._lock:
            self.clips = [c for c in self.clips if c.get("id") != clip_id]
            clip_folder = self.clips_dir / clip_id
            if clip_folder.exists():
                try:
                    shutil.rmtree(clip_folder)
                    return True
                except Exception as e:
                    logger.warning("Failed deleting clip folder %s: %s", clip_id, e)
            return True

    def get_status(self) -> dict[str, Any]:
        """Return the current Live Studio state."""
        elapsed = 0.0
        if self.session_active and self.session_start_time:
            elapsed = time.time() - self.session_start_time

        buf_dur = self.buffer.get_window_duration() if self.buffer else 0.0
        buf_chunks = self.buffer.get_total_chunks() if self.buffer else 0

        return {
            "session_active": self.session_active,
            "status": self.status,
            "status_detail": self.status_detail,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "elapsed_seconds": round(elapsed, 1),
            "buffer_duration_seconds": round(buf_dur, 1),
            "buffer_chunks": buf_chunks,
            "auto_clip_enabled": self.auto_clip_enabled,
            "sensitivity": self.sensitivity,
            "metadata": self.stream_metadata,
            "clips_count": len(self.clips),
        }

    def get_recent_transcripts(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.recent_transcripts)

    def get_clips(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.clips)

    def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        entry = {
            "type": event_type,
            "data": data,
            "time": time.time(),
        }
        self.live_events.append(entry)
        if len(self.live_events) > 200:
            self.live_events.pop(0)


# Module-level singleton instance
_LIVE_MANAGER: Optional[LiveStudioManager] = None
_INIT_LOCK = threading.Lock()


def get_live_manager(data_dir: Path, ffmpeg_bin: str, python_bin: str) -> LiveStudioManager:
    global _LIVE_MANAGER
    with _INIT_LOCK:
        if _LIVE_MANAGER is None:
            _LIVE_MANAGER = LiveStudioManager(
                data_dir=data_dir,
                ffmpeg_bin=ffmpeg_bin,
                python_bin=python_bin,
            )
        return _LIVE_MANAGER
