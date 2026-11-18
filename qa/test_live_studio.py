"""Unit tests for Live Studio real-time ingestion, rolling buffer, and highlight detection."""

import tempfile
import unittest
from pathlib import Path

from live.highlight_detector import HighlightDetector, CATEGORIES
from live.rolling_buffer import RollingBuffer
from live.stream_connector import StreamConnector
from live.studio_manager import LiveStudioManager
from live.transcriber import LiveTranscriptSegment


class TestLiveStudio(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_stream_connector_validation(self):
        # YouTube validation
        conn_yt_valid = StreamConnector("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", self.root, "ffmpeg")
        valid, msg = conn_yt_valid.validate()
        self.assertTrue(valid)

        conn_yt_invalid = StreamConnector("youtube", "invalid_url", self.root, "ffmpeg")
        valid, msg = conn_yt_invalid.validate()
        self.assertFalse(valid)

        # TikTok validation
        conn_tt = StreamConnector("tiktok", "@streamer", self.root, "ffmpeg")
        valid, msg = conn_tt.validate()
        self.assertTrue(valid)

        # OBS validation
        conn_obs = StreamConnector("obs", "", self.root, "ffmpeg")
        valid, msg = conn_obs.validate()
        self.assertTrue(valid)

    def test_rolling_buffer_management(self):
        buf = RollingBuffer(
            buffer_dir=self.root / "buffer",
            ffmpeg_bin="ffmpeg",
            max_duration_sec=30, # 30s window
            max_disk_mb=50,
        )

        # Create dummy segment files
        chunk1 = self.root / "buffer" / "chunk_00000.mp4"
        chunk1.write_bytes(b"x" * 2048)
        c1 = buf.add_chunk(chunk1, 0, stream_elapsed=5.0, duration=5.0)

        chunk2 = self.root / "buffer" / "chunk_00001.mp4"
        chunk2.write_bytes(b"x" * 2048)
        c2 = buf.add_chunk(chunk2, 1, stream_elapsed=10.0, duration=5.0)

        self.assertEqual(buf.get_total_chunks(), 2)
        self.assertAlmostEqual(buf.get_window_duration(), 10.0, delta=0.5)

        # Add chunk far in the future to trigger pruning
        chunk_far = self.root / "buffer" / "chunk_00010.mp4"
        chunk_far.write_bytes(b"x" * 2048)
        buf.add_chunk(chunk_far, 10, stream_elapsed=100.0, duration=5.0)

        # Old chunks should be pruned
        self.assertLess(buf.get_total_chunks(), 3)
        self.assertFalse(chunk1.exists())

    def test_heuristic_highlight_detection(self):
        detector = HighlightDetector(sensitivity=5)

        # Test gaming highlight
        segments = [
            LiveTranscriptSegment(start_sec=10.0, end_sec=15.0, text="Oh my god he clutched that pentakill!"),
            LiveTranscriptSegment(start_sec=15.0, end_sec=20.0, text="Unbelievable play, let's go!"),
        ]

        candidate = detector.evaluate(segments)
        self.assertIsNotNone(candidate)
        self.assertIn(candidate.category, CATEGORIES)
        self.assertGreaterEqual(candidate.score, 6.0)

        # Test quiet / non-highlight speech
        boring_segments = [
            LiveTranscriptSegment(start_sec=200.0, end_sec=205.0, text="So today is Wednesday afternoon."),
            LiveTranscriptSegment(start_sec=205.0, end_sec=210.0, text="We are looking at the document now."),
        ]
        non_candidate = detector.evaluate(boring_segments)
        self.assertIsNone(non_candidate)

    def test_studio_manager_obs_config(self):
        mgr = LiveStudioManager(
            data_dir=self.root,
            ffmpeg_bin="ffmpeg",
            python_bin="python",
        )
        obs_conf = mgr.get_obs_config()
        self.assertIn("server", obs_conf)
        self.assertIn("rtmp://127.0.0.1", obs_conf["server"])
        self.assertIn("stream_key", obs_conf)

    def test_studio_manager_status(self):
        mgr = LiveStudioManager(
            data_dir=self.root,
            ffmpeg_bin="ffmpeg",
            python_bin="python",
        )
        status = mgr.get_status()
        self.assertFalse(status["session_active"])
        self.assertEqual(status["status"], "idle")
        self.assertIn("buffer_duration_seconds", status)


if __name__ == "__main__":
    unittest.main()
