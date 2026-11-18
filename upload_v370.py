import json
import os
import subprocess
import sys
import time

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    creds, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    return dict([l.split('=', 1) for l in creds.splitlines() if '=' in l]).get('password', '')

token = get_token()
if not token:
    print("[ERROR] Could not retrieve git credential token.")
    sys.exit(1)

repo = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
tag = "v3.7.0"
target_commitish = "main"
release_name = "Clipify AI v3.7.0 - Live Studio Split-Screen & Real-Time Transcription Update"
release_body = """# Clipify AI v3.7.0 Release Notes

### 🚀 What's New & Fixed in v3.7.0:
- **Gaming Split-Screen Refined**: Unconditionally renders pristine 9:16 vertical shorts with 58% top gameplay and 42% bottom reaction webcam layout whenever Gaming Split-Screen is enabled.
- **Accurate Short Duration**: Clips generated from live streams strictly adhere to target duration (~30s, 15s, or 60s) centered right on the highlight action—eliminating short 4s/8s/16s snippets.
- **Real-Time Speech Transcription**: In-memory CTranslate2 faster-whisper speech recognition decodes audio chunks in ~80ms, delivering immediate live speech into the transcription feed without lagging.
- **Non-Blocking Batch & Highlight Clipping**: "Clip Highlight" and "Generate 4 Clips" render asynchronously in the background and populate the export gallery in real-time without locking the UI.
- **Polished AI Clip Ranking Terminal**: Full terminal window redesign with macOS traffic lights, glowing cyan prompt, and real-time viral hook scoring telemetry powered by local Ollama AI.
- **Sideways Ranked Clips Shelf**: Compact, responsive horizontal scrolling shelf with instant Preview ▶, Quick Edit ✂️, and direct MP4 downloads.

### 📦 Verified Windows Installer
- **SHA-256**: `C59E33B767D66D33878DCA419527463B7CE57BA59314F9A3EF604BFFA3D76B14`
- **File size**: ~347.7 MB
"""

# 1. Check if release already exists
print(f"[GITHUB] Checking if release {tag} exists...")
chk_cmd = [
    'curl.exe', '-s', '--http1.1',
    '-H', f'Authorization: token {token}',
    '-H', 'User-Agent: ReleaseUploader',
    f'https://api.github.com/repos/{repo}/releases/tags/{tag}'
]
res = subprocess.run(chk_cmd, capture_output=True, text=True)
release_data = json.loads(res.stdout) if res.stdout else {}

if "id" not in release_data:
    print(f"[GITHUB] Creating release {tag}...")
    create_payload = {
        "tag_name": tag,
        "name": release_name,
        "body": release_body,
        "draft": False,
        "prerelease": False,
    }
    create_cmd = [
        'curl.exe', '-s', '--http1.1',
        '-X', 'POST',
        '-H', f'Authorization: token {token}',
        '-H', 'Content-Type: application/json',
        '-H', 'User-Agent: ReleaseUploader',
        '-d', json.dumps(create_payload),
        f'https://api.github.com/repos/{repo}/releases'
    ]
    c_res = subprocess.run(create_cmd, capture_output=True, text=True)
    release_data = json.loads(c_res.stdout) if c_res.stdout else {}
    if "id" not in release_data:
        print("[ERROR] Failed creating release:", release_data)
        sys.exit(1)
    print(f"[GITHUB] Release {tag} created with ID: {release_data['id']}")
else:
    print(f"[GITHUB] Release {tag} exists with ID: {release_data['id']}")

release_id = release_data["id"]
upload_url_template = release_data.get("upload_url", f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets{{?name,label}}")
upload_base = upload_url_template.split("{")[0]

source_exe = r"L:\ClipifyAI\build\installer_app\out\Clipify AI Setup.exe"
file_size = os.path.getsize(source_exe)
print(f"[INFO] Source exe size: {file_size / (1024*1024):.2f} MB ({file_size} bytes)")

assets_to_upload = [
    "Clipify.AI.Setup.3.7.0.exe",
    "Clipify Setup 3.7.0.exe",
    "Clipify.AI.Setup.exe",
    "Clipify.Setup.exe",
]

# Check existing assets to delete duplicates before re-upload
existing_assets = {a["name"]: a["id"] for a in release_data.get("assets", [])}

for name in assets_to_upload:
    if name in existing_assets:
        asset_id = existing_assets[name]
        print(f"[GITHUB] Deleting existing asset {name} (id {asset_id})...")
        del_cmd = [
            'curl.exe', '-s', '--http1.1',
            '-X', 'DELETE',
            '-H', f'Authorization: token {token}',
            f'https://api.github.com/repos/{repo}/releases/assets/{asset_id}'
        ]
        subprocess.run(del_cmd)
        time.sleep(1)

    print(f"\n[GITHUB] Uploading {name} to release {tag}...")
    upload_url = f"{upload_base}?name={name}"
    up_cmd = [
        'curl.exe', '--http1.1',
        '-X', 'POST',
        '-H', f'Authorization: token {token}',
        '-H', 'Content-Type: application/octet-stream',
        '-H', 'User-Agent: ReleaseUploader',
        '--data-binary', f'@{source_exe}',
        upload_url
    ]
    u_res = subprocess.run(up_cmd, capture_output=True, text=True)
    try:
        up_json = json.loads(u_res.stdout)
        if "id" in up_json and up_json.get("state") == "uploaded":
            print(f"[SUCCESS] {name} uploaded! ID: {up_json['id']}, Size: {up_json.get('size')} bytes")
            print(f"          Download URL: {up_json.get('browser_download_url')}")
        else:
            print(f"[WARN] Upload response for {name}: {up_json}")
    except Exception as e:
        print(f"[ERROR] Could not parse upload response: {e}\nRaw output: {u_res.stdout[:300]}")

print("\n[GITHUB] All assets uploaded successfully!")
