"""Clipify AI - Live Studio Package.

Provides real-time livestream ingestion (YouTube Live, TikTok Live, OBS Studio),
rolling buffer management, incremental speech transcription, local Ollama highlight
detection, and automatic 9:16 vertical / 16:9 MP4 short generation while the stream runs.
"""

from live.studio_manager import LiveStudioManager, get_live_manager

__all__ = ["LiveStudioManager", "get_live_manager"]
