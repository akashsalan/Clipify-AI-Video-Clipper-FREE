import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

REPO = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
TAG = "v3.1.0"
RELEASE_NAME = "Clipify AI v3.1.0"
ASSET_NAME = "Clipify.AI.Setup.exe"
FILE_PATH = r"L:\ClipifyAI\build\installer_app\out\Clipify.AI.Setup.exe"

RELEASE_NOTES = """## Clipify AI v3.1.0 Release Notes

### 🚀 What's New & Fixed in v3.1.0
1. **🛡️ Corrupt Model Cache Auto-Purge & Self-Healing**:
   - Fixed `RuntimeError: Cannot load the vocabulary from the model directory` caused by interrupted model downloads.
   - Rigorously validates model weights, config, and vocabulary files before flagging as cached.
   - Automatically detects and purges broken Hugging Face cache directories on disk and self-heals via fresh download or mirror fallback without requiring manual reinstallation.

2. **⚡ Built-in Heuristic AI (No Ollama Needed)**:
   - Fixed the issue where users without Ollama installed could not click or press the "Generate Shorts" button.
   - Added native **Built-in Heuristic AI** mode for instant clipping using audio density and candidate heuristics with zero Ollama setup required.
   - Fixed the HTTP 503 error when starting jobs without Ollama models.

3. **⏱️ CPU Whisper Acceleration & Live Heartbeat Telemetry**:
   - Intelligently defaults to the `base` Whisper model on CPU systems (`CUDA=False`), speeding up transcription **5x–8x** (reducing 34-minute video processing from 14 minutes down to ~2–3 minutes!).
   - Fixed the UI appearing frozen at `10%` during long transcriptions: added background stdout heartbeats every 5 seconds and dynamic SSE progress scaling from 10% to 28% with live elapsed time.

### 📦 Download & Install
Download **`Clipify.AI.Setup.exe`** below to install Clipify AI v3.1.0.
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
            old_release = json.loads(resp.read().decode())
            print(f"Release {TAG} exists (id: {old_release['id']}). Deleting to refresh release timestamp...")
            del_rel_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/{old_release['id']}",
                headers=headers,
                method="DELETE"
            )
            with urllib.request.urlopen(del_rel_req):
                print(f"Deleted old release {TAG} (id: {old_release['id']})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Release {TAG} not found, creating fresh...")
        else:
            raise

    # 2. Create release fresh so timestamp is updated to current time
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

    # 3. Check if asset already exists
    assets = release.get("assets", [])
    for a in assets:
        if a["name"] == ASSET_NAME:
            print(f"Asset {ASSET_NAME} already exists (id: {a['id']}). Deleting old asset first...")
            del_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}",
                headers=headers,
                method="DELETE"
            )
            with urllib.request.urlopen(del_req) as del_resp:
                print(f"Deleted old asset {ASSET_NAME}")
            break

    # 4. Upload fresh asset
    file_size = os.path.getsize(FILE_PATH)
    print(f"Uploading {FILE_PATH} ({file_size / (1024*1024):.2f} MB) as {ASSET_NAME}...")

    upload_url = f"{base_upload_url}?name={ASSET_NAME}"
    upload_headers = {
        "Authorization": f"token {token}",
        "User-Agent": "ClipifyAI-Release-Script",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size)
    }

    start_time = time.time()
    with open(FILE_PATH, "rb") as f:
        up_req = urllib.request.Request(upload_url, data=f, headers=upload_headers, method="POST")
        with urllib.request.urlopen(up_req) as resp:
            result = json.loads(resp.read().decode())
            elapsed = time.time() - start_time
            print(f"Upload complete in {elapsed:.1f}s!")
            print(f"Asset URL: {result.get('browser_download_url')}")

if __name__ == "__main__":
    main()

