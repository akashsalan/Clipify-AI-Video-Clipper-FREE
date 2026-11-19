"""Background YouTube uploads for newly rendered Live Studio Shorts."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Callable

from tools.mcp_publish import publish_youtube_short

logger = logging.getLogger(__name__)


class LiveYouTubeUploads:
    def __init__(self, clips_dir: Path, privacy: str, log_activity: Callable[[str, str], None]):
        self.clips_dir = clips_dir
        self.database = clips_dir.parent / "youtube_uploads.sqlite3"
        self.privacy = privacy
        self.log_activity = log_activity
        self.wake = threading.Event()
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    clip_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    result TEXT
                )
            """)
        threading.Thread(target=self._run, name="live-youtube-uploads", daemon=True).start()
        self.wake.set()

    def _connect(self):
        return closing(sqlite3.connect(self.database, isolation_level=None))

    def enqueue(self, clip_id: str, title: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO uploads (clip_id, title) VALUES (?, ?)", (clip_id, title))
        self.wake.set()

    def _run(self) -> None:
        while True:
            self.wake.wait()
            self.wake.clear()
            try:
                self._drain()
            except Exception:
                logger.exception("Live Studio YouTube queue failed")
                self.log_activity("YouTube upload queue failed. Check the app log.", "error")

    def _drain(self) -> None:
        while True:
            with self._connect() as db:
                job = db.execute("""
                    UPDATE uploads SET state = 'uploading'
                    WHERE rowid = (
                        SELECT rowid FROM uploads WHERE state = 'pending' ORDER BY rowid LIMIT 1
                    )
                    RETURNING clip_id, title
                """).fetchone()
            if job is None:
                return
            self._upload(*job)

    def _upload(self, clip_id: str, title: str) -> None:
        video = self.clips_dir / clip_id / "short_9_16.mp4"
        self.log_activity(f"YouTube upload started for clip {clip_id}.", "info")
        result = publish_youtube_short(
            str(video), title, privacy=self.privacy, require_refresh=True,
        )
        if result.get("status") == "published" and result.get("video_id"):
            state, detail = "uploaded", result["url"]
        else:
            state = "failed"
            detail = result.get("error", "YouTube did not return a video ID.")
        with self._connect() as db:
            db.execute(
                "UPDATE uploads SET state = ?, result = ? WHERE clip_id = ?",
                (state, detail, clip_id),
            )
        level = "success" if state == "uploaded" else "error"
        self.log_activity(f"YouTube upload {state} for clip {clip_id}. {detail}", level)
