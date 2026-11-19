import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from live.clip_generator import LiveClipGenerator
from live.youtube_uploads import LiveYouTubeUploads
from tools.mcp_publish import publish_youtube_short


class LiveYouTubeUploadsTests(unittest.TestCase):
    def test_render_enqueues_the_finished_vertical_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            def stitch(_start, _end, path, **_kwargs):
                path.write_bytes(b"x" * 2048)
                return True

            decision = Mock(layout="gaming", content_type="gaming", face_tracked=False,
                            facecam_detected=False, captions_applied=False, caption_style="none",
                            energy_zoom=False, badges=[])

            def render(*, output_vertical, **_kwargs):
                output_vertical.write_bytes(b"x" * 2048)
                return decision

            clips_dir = Path(directory)
            buffer = Mock(extract_stitched_video=stitch)

            completed = []

            def verify_ready(clip_id, _title):
                clip_dir = clips_dir / clip_id
                completed.append(
                    (clip_dir / "short_9_16.mp4").is_file() and (clip_dir / "meta.json").is_file()
                )

            ready = Mock(side_effect=verify_ready)
            with patch("live.clip_generator.SmartEditor") as editor, patch("live.clip_generator.subprocess.run"):
                editor.return_value.edit.side_effect = render
                generator = LiveClipGenerator("ffmpeg", buffer, clips_dir, on_short_ready=ready)
                clip = generator.render_clip(0, 30, "Gaming highlight", "gaming")
                editor.return_value.edit.side_effect = None
                editor.return_value.edit.return_value = decision
                generator.render_clip(0, 30, "Failed vertical render", "gaming")
            ready.assert_called_once_with(clip["id"], "Gaming highlight")
            self.assertEqual(completed, [True])

    def test_pending_clip_survives_restart_and_uploads_once(self):
        with tempfile.TemporaryDirectory() as directory:
            clips_dir = Path(directory) / "clips"
            with patch("live.youtube_uploads.threading.Thread"), patch(
                "live.youtube_uploads.publish_youtube_short",
                return_value={"status": "published", "video_id": "abc", "url": "https://www.youtube.com/shorts/abc"},
            ) as publish:
                first = LiveYouTubeUploads(clips_dir, "private", Mock())
                first.enqueue("clip1", "A highlight")
                restarted = LiveYouTubeUploads(clips_dir, "private", Mock())
                restarted._drain()
                restarted.enqueue("clip1", "Duplicate clip")
                restarted._drain()
                publish.assert_called_once_with(
                    str(clips_dir / "clip1" / "short_9_16.mp4"),
                    "A highlight", privacy="private", require_refresh=True,
                )

    def test_failed_and_interrupted_uploads_are_not_reposted(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("live.youtube_uploads.threading.Thread"), patch(
                "live.youtube_uploads.publish_youtube_short",
                return_value={"ok": False, "error": "Connection lost"},
            ) as publish:
                uploads = LiveYouTubeUploads(Path(directory) / "clips", "private", Mock())
                uploads.enqueue("interrupted", "Interrupted")
                uploads.enqueue("failed", "Failed")
                with sqlite3.connect(uploads.database) as database:
                    database.execute("UPDATE uploads SET state = 'uploading' WHERE clip_id = 'interrupted'")
                database.close()
                uploads._drain()
                uploads._drain()
                self.assertEqual(publish.call_count, 1)
                self.assertEqual(publish.call_args.args[1], "Failed")


class YouTubeOAuthTests(unittest.TestCase):
    def test_auto_upload_refreshes_token_and_uploads_with_private_visibility(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "short_9_16.mp4"
            video.write_bytes(b"short")
            token_response = BytesIO(b'{"access_token": "fresh-token"}')
            init_response = BytesIO()
            init_response.headers = {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"}
            upload_response = BytesIO(b'{"id": "abc"}')
            credentials = {"youtube": {
                "client_id": "client", "client_secret": "secret",
                "refresh_token": "refresh", "access_token": "stale",
            }}
            with patch("tools.mcp_publish.load_credentials", return_value=credentials), patch(
                "tools.mcp_publish.urllib.request.urlopen",
                side_effect=[token_response, init_response, upload_response],
            ) as open_url:
                result = publish_youtube_short(str(video), "Highlight", privacy="private", require_refresh=True)
            self.assertEqual(result["video_id"], "abc")
            refresh, init, upload = [call.args[0] for call in open_url.call_args_list]
            self.assertEqual(parse_qs(refresh.data.decode())["grant_type"], ["refresh_token"])
            self.assertEqual(init.get_header("Authorization"), "Bearer fresh-token")
            self.assertEqual(json.loads(init.data)["status"]["privacyStatus"], "private")
            self.assertEqual(upload.get_method(), "PUT")
            self.assertEqual(upload.get_header("Authorization"), "Bearer fresh-token")

    def test_auto_upload_requires_refresh_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "short_9_16.mp4"
            video.touch()
            with patch("tools.mcp_publish.load_credentials", return_value={"youtube": {"access_token": "stale"}}), patch(
                "tools.mcp_publish.urllib.request.urlopen",
            ) as open_url:
                result = publish_youtube_short(str(video), "Highlight", require_refresh=True)
            self.assertFalse(result["ok"])
            open_url.assert_not_called()
