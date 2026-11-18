"""Incremental speech transcription for Clipify AI Live Studio.

Reuses the existing local WhisperX / Whisper pipeline to transcribe
live audio segments as they arrive, emitting timestamped utterances.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("clipify.live.transcriber")


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass
class LiveTranscriptSegment:
    start_sec: float
    end_sec: float
    text: str
    speaker: str = "Host"
    confidence: float = 1.0


class LiveTranscriber:
    """Manages incremental transcription of incoming live stream chunks."""

    def __init__(
        self,
        python_bin: str,
        ffmpeg_bin: str,
        model_name: str = "base",
        device: str = "cpu",
        on_segment: Optional[Callable[[LiveTranscriptSegment], None]] = None,
    ):
        self.python_bin = python_bin
        self.ffmpeg_bin = ffmpeg_bin
        self.model_name = model_name
        self.device = device
        self.on_segment = on_segment

        self.audio_queue: queue.Queue[tuple[Path, float, float]] = queue.Queue(maxsize=100)
        self.transcripts: list[LiveTranscriptSegment] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._model_instance: Any = None

    def start(self) -> None:
        """Start the background transcription processor."""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        """Stop transcription processing."""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=3)
            self._worker_thread = None

    def enqueue_chunk(self, chunk_wav_path: Path, start_sec: float, duration: float) -> None:
        """Submit a newly extracted WAV segment for transcription."""
        try:
            self.audio_queue.put_nowait((chunk_wav_path, start_sec, duration))
        except queue.Full:
            logger.warning("Live audio transcription queue is full; dropping chunk")

    def get_recent_transcripts(self, last_n_seconds: float = 300.0) -> list[LiveTranscriptSegment]:
        """Retrieve transcribed utterances within the last N seconds."""
        with self._lock:
            if not self.transcripts:
                return []
            latest_time = self.transcripts[-1].end_sec
            min_time = latest_time - last_n_seconds
            return [s for s in self.transcripts if s.end_sec >= min_time]

    def get_full_transcript_text(self) -> str:
        """Return full text transcribed so far."""
        with self._lock:
            return " ".join(s.text for s in self.transcripts)

    def _worker_loop(self) -> None:
        """Pulls audio chunks from the queue and transcribes them."""
        # Ensure OpenMP stack size is safe
        os.environ.setdefault("OMP_STACKSIZE", "64M")
        os.environ.setdefault("KMP_STACKSIZE", "64M")

        while not self._stop_event.is_set():
            try:
                item = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            wav_path, chunk_start, chunk_duration = item
            try:
                segments = self._transcribe_wav(wav_path, chunk_start)
                if segments:
                    with self._lock:
                        self.transcripts.extend(segments)
                    for seg in segments:
                        if self.on_segment:
                            try:
                                self.on_segment(seg)
                            except Exception as e:
                                logger.exception("Error in on_segment callback: %s", e)
            except Exception as e:
                logger.debug("Transcription error for chunk %s: %s", wav_path.name, e)
            finally:
                self.audio_queue.task_done()
                # Clean up temporary WAV file
                try:
                    if wav_path.exists():
                        wav_path.unlink()
                except Exception:
                    pass

    def _transcribe_wav(self, wav_path: Path, chunk_start: float) -> list[LiveTranscriptSegment]:
        """Transcribe an isolated 16kHz WAV file."""
        if not wav_path.exists() or wav_path.stat().st_size < 1000:
            return []

        # Run whisper inline via python script for memory isolation
        code = f"""
import os, sys, json
os.environ['OMP_STACKSIZE'] = '64M'
os.environ['KMP_STACKSIZE'] = '64M'
os.environ['OMP_NUM_THREADS'] = '2'

try:
    import whisperx
    device = '{self.device}'
    compute_type = 'int8' if device == 'cpu' else 'float16'
    model = whisperx.load_model('{self.model_name}', device, compute_type=compute_type)
    audio = whisperx.load_audio(r'{str(wav_path)}')
    result = model.transcribe(audio, batch_size=4)
    print('JSON:' + json.dumps(result.get('segments', [])))
except Exception as e:
    try:
        import whisper
        model = whisper.load_model('{self.model_name}')
        result = model.transcribe(r'{str(wav_path)}')
        print('JSON:' + json.dumps(result.get('segments', [])))
    except Exception as e2:
        print('ERR:' + str(e2))
"""
        proc = subprocess.run(
            [self.python_bin, "-c", code],
            capture_output=True, text=True,
            timeout=40, creationflags=_hidden_flags(),
        )

        segments: list[LiveTranscriptSegment] = []
        for line in proc.stdout.splitlines():
            if line.startswith("JSON:"):
                try:
                    raw_segs = json.loads(line[5:])
                    for s in raw_segs:
                        text = s.get("text", "").strip()
                        if text:
                            seg_start = chunk_start + float(s.get("start", 0.0))
                            seg_end = chunk_start + float(s.get("end", 0.0))
                            segments.append(
                                LiveTranscriptSegment(
                                    start_sec=seg_start,
                                    end_sec=max(seg_end, seg_start + 0.5),
                                    text=text,
                                )
                            )
                except Exception as ex:
                    logger.debug("Failed parsing whisper output: %s", ex)

        return segments
