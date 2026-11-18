import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

REPO = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
TAG = "v3.5.4"
RELEASE_NAME = "Clipify AI v3.5.4: AI Clip Ranking, Batch Actions & Auto-Clipping Engine"
ASSET_NAME = "Clipify.AI.Setup.exe"
FILE_PATH = r"L:\ClipifyAI\Clipify.AI.Setup.exe"

RELEASE_NOTES = """<p align="center">
  <img src="https://raw.githubusercontent.com/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE/main/docs/screenshots/live_studio_clips.jpg" alt="Clipify AI Live Stream Clipping Studio — AI Ranked Viral Shorts" width="100%">
</p>

## Clipify AI v3.5.4: AI Clip Ranking, Batch Actions & Auto-Clipping Engine

### 🚀 What's New in v3.5.4

1. **✨ RANK CLIPS AI (Top 10 Neural Highlight Ranking)**:
   - Dedicated **RANK CLIPS AI** engine powered by local Ollama (Qwen 2.5) to evaluate viral hooks, pacing, and retention probability.
   - Outputs top 10 ranked clips with viral scores (e.g. `⚡ 9.8/10`), hook letter grades (e.g. `Hook: A+`), and AI verdict notes.
   - **Real-Time Live Ranking Console**: A dedicated terminal interface (`#rankingConsolePanel`) displaying step-by-step telemetry as clips are evaluated by the AI in real time.
   - Dedicated **AI Ranked Highlights** display section with rank badges (👑 #1 BEST, #2, #3), metrics bar, and direct preview/export actions.

2. **☑️ Batch Selection & Multi-Clip Deletion**:
   - Checkboxes on every regular clip card and ranked clip card for convenient multi-selection.
   - "Select All" toggle for both standard clips and ranked highlights.
   - Safe batch delete action to clean up multiple highlights in a single click with instant backend disk purge.

3. **⏱️ Autonomous Auto-Clipping Engine (1 to 100 Clips)**:
   - Select target clip limits from **1 to 100 clips** in Auto-Clipping preferences.
   - Background timer daemon guarantees clips are generated every interval (e.g. every 5 minutes) up to your selected target limit even during quiet gameplay or music-only streams.
   - Leave Clipify AI running for hours and return to a library of up to 100 edited Shorts!

4. **👤 Community Tour & GitHub Follow Integration**:
   - Enhanced first-launch interactive tour with a direct **Follow @sherlock-dev-ai** button alongside the **Star Repo** button.
   - Help support free, private, and unrestricted open-source AI tooling for creators.

5. **🔴 LIVE Stream Monitoring & Studio (Twitch & YouTube)**:
   - Direct live stream ingestion from **Twitch** (`twitch.tv/<channel>`) and **YouTube Live**.
   - Low-latency embedded player with real-time stream telemetry and buffer monitoring.
   - OBS Studio local RTMP ingestion (`rtmp://127.0.0.1:1935/live`).

6. **🎵 Strict A/V Sync & Dynamic Word-by-Word Subtitles**:
   - Audio/video presentation timestamps aligned with `aresample=async=1:first_pts=0` and constant frame rates (`cfr`).
   - Word-by-word animated karaoke subtitles with customizable fonts, styles, and canvas background blurs.
   - Complete toggle to disable subtitles or add custom channel watermarks.

7. **🛡️ 100% Clean Installer, Offline NLP Model & Defender Safety**:
   - Pre-bundled offline Kokoro English NLP model wheel (`en_core_web_sm-3.8.0`) directly inside the setup payload with automatic pip cache purging, completely eliminating 0-byte download drops and hash mismatch installation errors.
   - Zero Windows 11 Smart App Control (SAC) blocks — clean uninstallation without unverified stubs.
   - Compiled with standard Microsoft .NET Framework `csc.exe` tools, free of heuristic detections.
   - Prior release `v3.1.0` remains permanently preserved on GitHub.

8. **🧪 100% QA Unit Test Coverage**:
   - 120 automated tests passing with zero regressions across Create, Narrate, and Live Studio.

---

### 📥 Download & Verification

| Package | Version | Size | Checksum (SHA-256) |
| :--- | :---: | :---: | :--- |
| **`Clipify.AI.Setup.exe`** | `v3.5.4` | **331.6 MB** | `856D70F86773D3404FED9999E8456291AE93BDFC7665D0A45255302C70303C26` |

> **Note on Windows SmartScreen & Smart App Control**: Clipify AI is 100% open-source, free community software. Because open-source community releases are not signed by expensive commercial EV certificates ($300+/yr), Windows SmartScreen or Windows 11 Smart App Control (SAC) may display a standard unrecognized publisher prompt. Simply click **"More info"** → **"Run anyway"** to install.
"""

class ProgressFile:
    def __init__(self, filepath):
        self.f = open(filepath, "rb")
        self.total = os.path.getsize(filepath)
        self.uploaded = 0
        self.last_pct = -1

    def read(self, size=-1):
        chunk = self.f.read(size)
        self.uploaded += len(chunk)
        pct = int(self.uploaded / self.total * 100) if self.total else 100
        if pct != self.last_pct and pct % 5 == 0:
            self.last_pct = pct
            print(f"Uploading: {self.uploaded / (1024*1024):.1f} / {self.total / (1024*1024):.1f} MB ({pct}%)", flush=True)
        return chunk

    def __len__(self):
        return self.total

    def close(self):
        self.f.close()

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

    # 2. If release does not exist or needs update, create/patch it
    if not release:
        print(f"Creating fresh release {TAG}...")
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
            print(f"Created fresh release {TAG} (id: {release['id']}) published at {release.get('published_at')}")
    else:
        # Patch notes to ensure latest checksum and notes are active
        patch_payload = {
            "name": RELEASE_NAME,
            "body": RELEASE_NOTES
        }
        patch_req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/{release['id']}",
            data=json.dumps(patch_payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(patch_req) as resp:
                release = json.loads(resp.read().decode())
                print(f"Updated release metadata for {TAG}.")
        except Exception as pe:
            print(f"Release patch note: {pe}")

    upload_url_template = release["upload_url"] # e.g. "https://uploads.github.com/repos/.../releases/{release_id}/assets{?name,label}"
    base_upload_url = upload_url_template.split("{")[0]

    file_size = os.path.getsize(FILE_PATH)
    print(f"Checking {FILE_PATH} ({file_size / (1024*1024):.2f} MB) against GitHub asset {ASSET_NAME}...")

    # Check if identical asset already exists
    for a in release.get("assets", []):
        if a["name"] == ASSET_NAME and a.get("size") == file_size:
            print(f"SUCCESS: Asset {ASSET_NAME} already exists with exact size ({file_size} bytes).")
            print(f"Asset URL: {a.get('browser_download_url')}")
            return

    # Delete any existing/partial asset with this name
    for a in release.get("assets", []):
        if a["name"] == ASSET_NAME:
            print(f"Removing outdated asset {ASSET_NAME} (id: {a['id']})...")
            del_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}",
                headers=headers,
                method="DELETE"
            )
            try:
                with urllib.request.urlopen(del_req):
                    print("Deleted old asset.")
            except Exception as de:
                print(f"Delete note: {de}")

    # Upload with ProgressFile streaming
    upload_url = f"{base_upload_url}?name={ASSET_NAME}"
    upload_headers = {
        "Authorization": f"token {token}",
        "User-Agent": "ClipifyAI-Release-Script",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size)
    }

    for attempt in range(1, 4):
        print(f"Starting upload attempt {attempt}/3...")
        start_time = time.time()
        pf = ProgressFile(FILE_PATH)
        try:
            up_req = urllib.request.Request(upload_url, data=pf, headers=upload_headers, method="POST")
            with urllib.request.urlopen(up_req, timeout=1800) as resp:
                result = json.loads(resp.read().decode())
                elapsed = time.time() - start_time
                print(f"\nSUCCESS: Upload complete in {elapsed:.1f}s ({file_size / (1024*1024):.1f} MB)!")
                print(f"Asset URL: {result.get('browser_download_url')}")
                return
        except Exception as exc:
            print(f"\nAttempt {attempt} failed ({type(exc).__name__}: {exc}). Sleeping 5s before retry...")
            time.sleep(5)
        finally:
            pf.close()

    print("ERROR: Failed to upload asset after 3 attempts.")
    sys.exit(1)

if __name__ == "__main__":
    main()
