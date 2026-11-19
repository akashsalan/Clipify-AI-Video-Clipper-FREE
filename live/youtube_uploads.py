"""Background YouTube uploads for newly rendered Live Studio Shorts."""

from __future__ import annotations

import errno
import logging
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Callable

from tools.mcp_publish import publish_youtube_short

logger = logging.getLogger(__name__)


class LiveYouTubeUploads:
    def __init__(self, clips_dir: Path, privacy: str, log_activity: Callable[[str, str], None]):
        self.clips_dir = clips_dir
        self.database = clips_dir.parent / "youtube_uploads.sqlite3"
        self.lock_file = clips_dir.parent / "youtube_uploads.lock"
        self.privacy = privacy
        self.log_activity = log_activity
        self.wake = threading.Event()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    clip_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    session_url TEXT
                )
            """)
            if "session_url" not in {column[1] for column in db.execute("PRAGMA table_info(uploads)")}:
                db.execute("ALTER TABLE uploads ADD COLUMN session_url TEXT")
            db.commit()
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
            self.wake.wait(timeout=30)
            self.wake.clear()
            try:
                self._drain()
            except Exception:
                logger.exception("Live Studio YouTube queue failed")
                self.log_activity("YouTube upload queue failed. Check the app log.", "error")

    @contextmanager
    def _worker_lock(self):
        # The OS releases the lock on exit, allowing the next process to resume.
        with self.lock_file.open("a+b") as lock:
            lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EAGAIN, errno.EACCES}:
                    raise
                yield False
                return
            yield True

    def _drain(self) -> None:
        with self._worker_lock() as acquired:
            if not acquired:
                return
            while True:
                with self._connect() as db:
                    job = db.execute("""
                        UPDATE uploads SET state = 'active'
                        WHERE rowid = (
                            SELECT rowid FROM uploads WHERE state IN ('pending', 'active')
                            ORDER BY state = 'pending' DESC, rowid LIMIT 1
                        )
                        RETURNING clip_id, title, session_url
                    """).fetchone()
                if job is None or not self._upload(*job):
                    return

    def _upload(self, clip_id: str, title: str, session_url: str | None) -> bool:
        video = self.clips_dir / clip_id / "short_9_16.mp4"
        self.log_activity(f"YouTube upload started for clip {clip_id}.", "info")

        def save_session(url: str) -> None:
            with self._connect() as db:
                db.execute("UPDATE uploads SET session_url = ? WHERE clip_id = ?", (url, clip_id))

        result = publish_youtube_short(
            str(video), title, privacy=self.privacy, require_refresh=True,
            session_url=session_url, save_session=save_session,
        )
        if result.get("retryable"):
            self.log_activity(f"YouTube upload for clip {clip_id} will retry. {result['error']}", "warn")
            return False

        if result.get("status") == "published" and result.get("video_id"):
            state, detail = "uploaded", result["url"]
        else:
            state = "failed"
            detail = result.get("error", "YouTube did not return a video ID.")
        with self._connect() as db:
            db.execute(
                "UPDATE uploads SET state = ?, result = ?, session_url = NULL WHERE clip_id = ?",
                (state, detail, clip_id),
            )
        level = "success" if state == "uploaded" else "error"
        self.log_activity(f"YouTube upload {state} for clip {clip_id}. {detail}", level)
        return True
