"""Unit tests for Live Studio real-time ingestion, rolling buffer, and highlight detection."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

        # Twitch validation
        conn_tw = StreamConnector("twitch", "https://www.twitch.tv/ninja", self.root, "ffmpeg")
        valid, msg = conn_tw.validate()
        self.assertTrue(valid)

        conn_tw_empty = StreamConnector("twitch", "", self.root, "ffmpeg")
        valid, msg = conn_tw_empty.validate()
        self.assertFalse(valid)

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
        self.assertIn("editing_prefs", status)
        self.assertTrue(status["editing_prefs"]["auto_edit"])
        self.assertIn("console_logs", status)
        self.assertGreaterEqual(len(status["console_logs"]), 1)

    def test_studio_manager_console_and_auto_clip(self):
        mgr = LiveStudioManager(
            data_dir=self.root,
            ffmpeg_bin="ffmpeg",
            python_bin="python",
        )
        mgr.log_activity("Test message for console", "info")
        logs = mgr.get_console_logs()
        self.assertTrue(any("Test message for console" in l["message"] for l in logs))

        mgr.update_editing_prefs({"auto_clip_interval": 10})
        self.assertEqual(mgr.auto_clip_interval, 10)

    def test_caption_styler_presets(self):
        from live.caption_styler import CaptionStyler, PRESETS
        styler = CaptionStyler()
        transcripts = [
            {"start": 0.0, "end": 2.0, "text": "Unbelievable victory and clutch play!"},
            {"start": 2.5, "end": 4.5, "text": "Subscribe for more live content."},
        ]

        # Test each preset generates valid ASS file
        for preset_name in PRESETS.keys():
            ass_path = self.root / f"sub_{preset_name}.ass"
            res = styler.build_ass(
                transcripts=transcripts,
                clip_start=0.0,
                clip_duration=5.0,
                output_ass_path=str(ass_path),
                style_preset=preset_name,
                layout_mode="gaming_split" if preset_name == "gaming" else "talking_head",
            )
            self.assertIsNotNone(res)
            self.assertTrue(ass_path.exists())
            content = ass_path.read_text(encoding="utf-8-sig")
            self.assertIn("[Script Info]", content)
            self.assertIn("PlayResX: 1080", content)
            self.assertIn("PlayResY: 1920", content)
            self.assertIn("Dialogue:", content)

    def test_face_tracker_smoothing(self):
        from live.face_tracker import FaceTracker
        tracker = FaceTracker(target_aspect_w=9, target_aspect_h=16, smoothing_alpha=0.3, deadzone_ratio=0.05)
        # Verify initial target center
        self.assertEqual(tracker.smoothed_center, 0.5)

        # Apply slight shift inside deadzone (<5%): smoothed center remains unchanged
        smoothed_1 = tracker.update_smoothed_center(0.52)
        self.assertEqual(smoothed_1, 0.5)

        # Apply significant shift outside deadzone (>5%): center smoothly shifts via EMA
        smoothed_2 = tracker.update_smoothed_center(0.70)
        self.assertGreater(smoothed_2, 0.5)
        self.assertLess(smoothed_2, 0.7)

    def test_studio_manager_editing_prefs(self):
        mgr = LiveStudioManager(
            data_dir=self.root,
            ffmpeg_bin="ffmpeg",
            python_bin="python",
        )
        updated = mgr.update_editing_prefs({
            "auto_edit": False,
            "caption_style": "creator",
        })
        self.assertFalse(updated["auto_edit"])
        self.assertEqual(updated["caption_style"], "creator")
        # Unspecified prefs retain defaults
        self.assertTrue(updated["face_tracking"])

    def test_batch_clip_inactive_session(self):
        mgr = LiveStudioManager(
            data_dir=self.root,
            ffmpeg_bin="ffmpeg",
            python_bin="python",
        )
        # Calling batch_clip on inactive session returns empty list safely
        clips = mgr.batch_clip(count=4, duration_sec=30)
        self.assertEqual(clips, [])

    def test_caption_styling_none_and_custom_text(self):
        from live.caption_styler import CaptionStyler
        styler = CaptionStyler()
        out_ass = self.root / "test_none.ass"
        # When style_preset="none" and no custom text, returns None
        res = styler.build_ass(
            transcripts=[{"text": "Hello world", "start": 0.0, "end": 2.0}],
            clip_start=0.0,
            clip_duration=10.0,
            output_ass_path=str(out_ass),
            style_preset="none",
        )
        self.assertIsNone(res)

        # When style_preset="none" BUT custom text is provided, generates ASS with watermark
        res_custom = styler.build_ass(
            transcripts=[{"text": "Hello world", "start": 0.0, "end": 2.0}],
            clip_start=0.0,
            clip_duration=10.0,
            output_ass_path=str(out_ass),
            style_preset="none",
            custom_text="LIVE · @MYCHANNEL",
            custom_text_pos="top-center",
            custom_text_color="#FF0000",
        )
        self.assertIsNotNone(res_custom)
        content = Path(res_custom).read_text(encoding="utf-8")
        self.assertIn("LIVE · @MYCHANNEL", content)
        self.assertIn("Style: CustomText", content)

    def test_caption_styling_custom_font(self):
        from live.caption_styler import CaptionStyler
        styler = CaptionStyler()
        out_ass = self.root / "test_font.ass"
        res = styler.build_ass(
            transcripts=[{"text": "Test captions", "start": 0.0, "end": 2.0}],
            clip_start=0.0,
            clip_duration=5.0,
            output_ass_path=str(out_ass),
            style_preset="highlight",
            custom_font="Impact",
        )
        self.assertIsNotNone(res)
        content = Path(res).read_text(encoding="utf-8")
        self.assertIn("Impact", content)

    def test_smart_editor_background_styles(self):
        from live.smart_editor import SmartEditor
        from live.content_analyzer import ContentProfile
        editor = SmartEditor(ffmpeg_bin="ffmpeg")
        dummy_profile = ContentProfile(mode="general", layout="blurred_frame", confidence=0.5, facecam_box=None, primary_face_x=0.5, secondary_face_x=None, faces_detected=0)

        # Test black canvas
        fc_black = editor._build_filter_complex(
            raw_video_path=Path("dummy.mp4"),
            layout="blurred_frame",
            profile=dummy_profile,
            ass_path=None,
            energy_zoom=False,
            background_style="solid_black",
        )
        self.assertIn("color=c=black:s=1080x1920:r=30[bg]", fc_black)

        # Test custom color
        fc_custom = editor._build_filter_complex(
            raw_video_path=Path("dummy.mp4"),
            layout="blurred_frame",
            profile=dummy_profile,
            ass_path=None,
            energy_zoom=False,
            background_style="custom_color",
            background_color="#1e293b",
        )
        self.assertIn("color=c='#1e293b':s=1080x1920:r=30[bg]", fc_custom)

        # Test heavy blur
        fc_heavy = editor._build_filter_complex(
            raw_video_path=Path("dummy.mp4"),
            layout="blurred_frame",
            profile=dummy_profile,
            ass_path=None,
            energy_zoom=False,
            background_style="heavy_blur",
        )
        self.assertIn("boxblur=45:5[bg]", fc_heavy)


if __name__ == "__main__":
    unittest.main()

