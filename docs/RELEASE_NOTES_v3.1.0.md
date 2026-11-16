# Clipify AI v3.1.0 Release Notes

**Release Date**: November 16, 2026  
**Tag**: `v3.1.0`  
**Package**: `Clipify.AI.Setup.exe` (Standalone Windows x64 Installer)

---

## 🚀 What's New & Fixed in v3.1.0

### 1. 🛡️ Corrupt Model Cache Auto-Purge & Self-Healing
- **The Issue**: When a user's network connection dropped or was interrupted during the initial Whisper model download, Hugging Face cached incomplete directories with missing or 0-byte `vocabulary.txt` / `tokenizer.json`. The app subsequently threw `RuntimeError: Cannot load the vocabulary from the model directory`.
- **The Fix**: 
  - `_is_cached()` now strictly verifies that model weights (`model.bin` / `model.safetensors` > 10 MB), configuration (`config.json` > 50 B), and vocabulary (`vocabulary.*` / `tokenizer.json` > 1 KB) are all valid and non-empty.
  - Added self-healing cache repair: if a vocabulary error is ever encountered, Clipify AI automatically purges the corrupted model folder from disk (`~/.cache/huggingface/hub/`), clears offline constraints, and seamlessly redownloads the clean weights (with mirror fallback) or switches cleanly to another verified cached model without crashing.

### 2. ⚡ Standalone Heuristic AI (No Ollama Needed) & Active Generate Button
- **The Issue**: When Ollama was not installed or running, the Generate Shorts button was hard-disabled with zero explanation, preventing users from creating clips.
- **The Fix**:
  - Clipify AI now supports **Built-in Fast Heuristic AI Mode** right from the AI Model picker: `⚡ Built-in Heuristic AI (No Ollama needed)`.
  - The Generate Shorts button is now active whenever a video is loaded (`create.disabled = !state.source`). Users can generate clips instantly using audio density and candidate heuristics even if they don't have Ollama or local LLMs installed.
  - If a user clicks the button before adding a video, a clear animated notice prompts them to upload a video or paste a YouTube link.

### 3. ⏱️ Hardware-Aware Whisper Model & Live Transcription Heartbeats
- **The Issue**: On systems without a dedicated NVIDIA GPU (`CUDA=False`), transcribing a long video (e.g. 34 minutes) on CPU with the heavy `medium` Whisper model took 13–15 minutes with zero console output, leaving the progress bar frozen at `10%` and appearing hung.
- **The Fix**:
  - **CPU Acceleration**: On CPU systems, Clipify AI now intelligently defaults to the `base` transcription model (running **5x–8x faster on CPU**, cutting a 34-minute transcription from 14 minutes down to ~2–3 minutes!). CUDA-enabled systems continue using `medium` for maximum accuracy.
  - **Live Heartbeat Telemetry**: A background heartbeat thread now continuously streams progress updates (`[Transcribe] Speech recognition in progress... (1m 15s elapsed · approx 35%)`) every 5 seconds.
  - **Dynamic Progress Updates**: The web UI now smoothly advances progress from 10% to 28% with live elapsed minutes/seconds (`Transcribing audio (1m 20s elapsed · processing speech)`) so users know the app is actively working.

---

## 📦 Download & Installation

Download **`Clipify.AI.Setup.exe`** from GitHub Releases:
- Direct Download: [Clipify.AI.Setup.exe](https://github.com/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE/releases/download/v3.1.0/Clipify.AI.Setup.exe)
- Documentation & Website: [https://ai.projectclipzy.workers.dev/](https://ai.projectclipzy.workers.dev/)
