"""Clipify AI - Live Studio Package.

Provides real-time livestream ingestion (YouTube Live, TikTok Live, OBS Studio),
rolling buffer management, incremental speech transcription, local Ollama highlight
detection, content analysis, face tracking, dynamic ASS caption styling,
and the Ultimate AI Live Clipping engine.
"""

from live.caption_styler import CaptionStyler
from live.clip_generator import LiveClipGenerator
from live.content_analyzer import ContentAnalyzer, ContentProfile
from live.face_tracker import FaceTracker
from live.highlight_detector import HighlightDetector
from live.rolling_buffer import RollingBuffer
from live.smart_editor import EditDecision, SmartEditor
from live.stream_connector import StreamConnector
from live.studio_manager import LiveStudioManager, get_live_manager
from live.transcriber import LiveTranscriber

__all__ = [
    "LiveStudioManager",
    "get_live_manager",
    "ContentAnalyzer",
    "ContentProfile",
    "FaceTracker",
    "CaptionStyler",
    "SmartEditor",
    "EditDecision",
    "LiveClipGenerator",
    "HighlightDetector",
    "RollingBuffer",
    "StreamConnector",
    "LiveTranscriber",
]
