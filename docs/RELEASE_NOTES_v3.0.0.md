# Clipify AI v3.0.0 Release Notes

**Clipify AI v3.0.0** is a major release featuring complete vertical framing overhauls, sub-millisecond voice preview caching, enhanced cliplist filtering, automated Ollama discovery, and an upgraded Electron/NSIS installer with real-time terminal telemetry and multi-season game mechanics.

---

## 🚀 Key Improvements & Changelog (from v2.0.0 to v3.0.0)

### 1. In-App Video Editor & Layout Framing
- **Expanded 9:16 Vertical Preview Frame**: Completely redesigned `.editor-preview-frame` to an expansive 9:16 vertical viewport (`height: min(78vh, 680px)`) with crisp `object-fit: contain` rendering. Videos now utilize available screen real estate without squishing or horizontal cropping.
- **Finished Shorts Card Aspect Ratio**: Corrected thumbnail aspect ratios and removed aggressive `cover` zooming to prevent face-clipping.
- **Interactive Project Navigation**: Fixed project card "Open" action to seamlessly route into the Editor with target project parameters pre-loaded.

### 2. Narrate Studio & Faceless Short Creation
- **Background Cliplist Filtering**: Excluded past generated clipping outputs from the Narrate background picker for a clean, distraction-free asset library.
- **Voice Preview Latency Optimization**: Added disk caching (`preview_sapi_*.wav`) and startup pre-warming for neural Kokoro ONNX and Windows SAPI voices, delivering cached previews in `< 2 ms`.
- **Dynamic Story Script Prompts**: Updated LLM script generation prompts to create attention-grabbing viral hooks with varying storylines instead of templated fills.

### 3. Smart 9:16 Auto-Cropping & Split Screen
- **Face & Speaker Centering**: Improved MediaPipe/OpenCV tracking routines for centering active speakers in 9:16 aspect ratio.
- **2-Panel Split Screen**: Refined dual-speaker and reaction/gameplay split-screen rendering with synchronized audio-visual alignment.

### 4. Interactive Installer & Telemetry (v3.0.0)
- **Interactive Runner Game**: Added dynamic procedural seasonal stages (Spring greens -> Autumn reds -> Winter snow -> Bare branches) synchronized to installation progress.
- **Live Terminal Console**: Integrated real-time console streaming so users can observe pip installations, model unpacking, and runtime setup steps live.
- **Ollama Engine Autodetection**: Added background model scanning and one-click model reload for seamless local AI engine detection.

---

## 📦 Verified Installer Package

- **File:** `Clipify.AI.Setup.exe`
- **Size:** 277,087,552 bytes (264.25 MB)
- **SHA-256:** `30F5E1AD72303AC5D00E708C0F0D86D73B1BEA0093CAF163FC93C01ABBEE553D`
- **Download Link:** [GitHub Releases v3.0.0](https://github.com/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE/releases/download/v3.0.0/Clipify.AI.Setup.exe)
