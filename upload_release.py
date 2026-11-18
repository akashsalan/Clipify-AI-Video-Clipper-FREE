import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

REPO = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
TAG = "v3.2.1"
RELEASE_NAME = "Clipify AI v3.2.1"
ASSET_NAME = "Clipify.AI.Setup.exe"
FILE_PATH = r"L:\ClipifyAI\build\installer_app\out\Clipify.AI.Setup.exe"

RELEASE_NOTES = """## Clipify AI v3.2.1 Release Notes

### 🚀 What's New in v3.2.1

1. **🔴 Live Studio [BETA] — Real-Time Stream Clipping Engine**:
   - Turn live broadcast moments into professionally edited vertical Shorts automatically.
   - **YouTube Live & OBS Studio RTMP Support**: Direct stream ingestion from any public YouTube Live URL or OBS Studio (`rtmp://127.0.0.1:1935/live`).
   - **Watch Like The Stream**: Integrated live player with direct audio and video playback, plus diagnostic snapshot frame feed.
   - **Rolling Media Buffer**: Maintain 5–20 minutes of rolling buffer with zero latency.
   - **Instant & Batch Clipping**: Dedicated `⚡ Clip Highlight` (15s, 30s, 60s) and `🎬 Generate 4 Clips` batch button to extract and render multiple high-energy Shorts simultaneously.

2. **🧠 Smart AI Shorts Video Editing**:
   - **Face Tracking & Stabilization**: Centroid speaker tracking with deadzone tolerance and exponential moving average (EMA) jitter smoothing.
   - **Gaming Split-Screen**: Automated layout combining 58% top gameplay with 42% bottom webcam/reaction.
   - **Dynamic Energy Zooms**: Automatic punch-in zooms on high-excitement conversational moments.

3. **🎨 Visual Customization, Fonts & Branding**:
   - **Custom Canvas Backgrounds**: Soft Ambient Blur, Heavy Cinematic Blur, Solid Black Canvas, or Custom Brand Color with hex/color picker.
   - **Custom Text & Watermarks**: Add persistent channel handle or tag (`LIVE · @CHANNEL`) with custom alignment (`Top Center`, `Top Left`, `Bottom Center`, etc.) and color.
   - **Font Library**: Choose from Montserrat Extra Bold, Arial Black, Impact, Segoe UI Black, Arial, Segoe UI, Trebuchet MS, Verdana, Calibri, Georgia.
   - **Disable Captions**: Option to disable burned-in subtitles completely while preserving watermarks and smart reframing.

4. **🛡️ Defender-Clean Native Launcher & SmartScreen Guide**:
   - Clean native C# wrappers (`WorkerLauncher.cs`, `Launcher.cs`) compiled with Microsoft `.NET Framework csc.exe`, eliminating heuristic false positives.
   - 100% free and open-source with zero malware or telemetry.
   - *Note on Windows SmartScreen*: Since this is a new open-source binary without an enterprise EV certificate, Windows Defender SmartScreen may show *"Windows protected your PC"*. Simply click **More info** → **Run anyway**.

5. **✨ Quality Assurance & Regressions**:
   - All 116 comprehensive QA unit tests passing.
   - Fully preserved Create, Narrate, Ollama, WhisperX, FFmpeg, and Python 3.11 runtime pipelines.

### 📦 Download & Install
Download **`Clipify.AI.Setup.exe`** below to install Clipify AI v3.2.1.
"""

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    creds, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    return dict([line.split('=', 1) for line in creds.splitlines() if '=' in line]).get('password', '')

def main():
    token = get_token()
    if not token:
        print("ERROR: No GitHub token found.")
        sys.exit(1)

    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "ClipifyAI-Release-Script",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1. Check if release already exists
    print(f"Checking if release {TAG} exists...")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}",
        headers=headers
    )
    release = None
    try:
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read().decode())
            print(f"Release {TAG} exists (id: {release['id']})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Release {TAG} not found, creating fresh...")
        else:
            raise

    # 2. Create release if not found
    if not release:
        payload = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": RELEASE_NAME,
            "body": RELEASE_NOTES,
            "draft": False,
            "prerelease": False
        }
        create_req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases",
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(create_req) as resp:
            release = json.loads(resp.read().decode())
            print(f"Created fresh release {TAG} (id: {release['id']}) with current timestamp")

    upload_url_template = release["upload_url"] # e.g. "https://uploads.github.com/repos/.../releases/{release_id}/assets{?name,label}"
    base_upload_url = upload_url_template.split("{")[0]

    file_size = os.path.getsize(FILE_PATH)
    print(f"Preparing to upload {FILE_PATH} ({file_size / (1024*1024):.2f} MB) as {ASSET_NAME}...")

    # Upload with retries
    for attempt in range(1, 6):
        # Refresh asset list
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/{release['id']}",
            headers=headers
        )
        try:
            with urllib.request.urlopen(req) as resp:
                rel_info = json.loads(resp.read().decode())
                for a in rel_info.get("assets", []):
                    if a["name"] == ASSET_NAME:
                        print(f"Removing existing asset {ASSET_NAME} (id: {a['id']})...")
                        del_req = urllib.request.Request(
                            f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}",
                            headers=headers,
                            method="DELETE"
                        )
                        with urllib.request.urlopen(del_req):
                            print("Deleted old asset.")
                        break
        except Exception as e:
            print(f"Asset check note: {e}")

        print(f"Upload attempt {attempt}/5...")
        upload_url = f"{base_upload_url}?name={ASSET_NAME}"
        upload_headers = {
            "Authorization": f"token {token}",
            "User-Agent": "ClipifyAI-Release-Script",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_size)
        }

        start_time = time.time()
        try:
            with open(FILE_PATH, "rb") as f:
                up_req = urllib.request.Request(upload_url, data=f, headers=upload_headers, method="POST")
                with urllib.request.urlopen(up_req, timeout=600) as resp:
                    result = json.loads(resp.read().decode())
                    elapsed = time.time() - start_time
                    print(f"SUCCESS: Upload complete in {elapsed:.1f}s!")
                    print(f"Asset URL: {result.get('browser_download_url')}")
                    return
        except Exception as exc:
            print(f"Attempt {attempt} failed ({type(exc).__name__}: {exc}). Sleeping 5s before retry...")
            time.sleep(5)

    print("ERROR: Failed to upload asset after 5 attempts.")
    sys.exit(1)

if __name__ == "__main__":
    main()

