import json
import os
import subprocess
import sys
import time
import urllib.parse
import hashlib

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    creds, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    return dict([l.split('=', 1) for l in creds.splitlines() if '=' in l]).get('password', '')

token = get_token()
if not token:
    print("[ERROR] Could not retrieve git credential token.", flush=True)
    sys.exit(1)

repo = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
tag = "v3.7.0"
rel_id = 450374034
source_exe = r"L:\ClipifyAI\build\installer_app\out\Clipify AI Setup.exe"

if not os.path.exists(source_exe):
    print("[ERROR] Source installer exe not found at", source_exe, flush=True)
    sys.exit(1)

file_size = os.path.getsize(source_exe)
with open(source_exe, "rb") as f:
    sha256_hash = hashlib.sha256(f.read()).hexdigest().upper()

print(f"[INFO] Source exe size: {file_size / (1024*1024):.2f} MB ({file_size} bytes)", flush=True)
print(f"[INFO] SHA-256: {sha256_hash}", flush=True)

# 1. Check existing assets in release and delete any old ones
chk_cmd = [
    'curl.exe', '-s', '--http1.1',
    '-H', f'Authorization: token {token}',
    '-H', 'User-Agent: ReleaseUploader',
    f'https://api.github.com/repos/{repo}/releases/{rel_id}/assets'
]
res = subprocess.run(chk_cmd, capture_output=True, text=True)
try:
    assets = json.loads(res.stdout) if res.stdout else []
    for a in assets:
        print(f"[GITHUB] Deleting existing asset {a['name']} (id {a['id']})...", flush=True)
        del_cmd = [
            'curl.exe', '-s', '-X', 'DELETE',
            '-H', f'Authorization: token {token}',
            f'https://api.github.com/repos/{repo}/releases/assets/{a["id"]}'
        ]
        subprocess.run(del_cmd, capture_output=True)
        time.sleep(1)
except Exception as e:
    print("Asset list error:", e, flush=True)

assets_to_upload = [
    "Clipify.AI.Setup.3.7.0.exe",
    "Clipify Setup 3.7.0.exe",
    "Clipify.AI.Setup.exe",
    "Clipify.Setup.exe",
]

for asset_name in assets_to_upload:
    encoded_name = urllib.parse.quote(asset_name)
    upload_url = f"https://uploads.github.com/repos/{repo}/releases/{rel_id}/assets?name={encoded_name}"
    print(f"\n[GITHUB] Uploading {asset_name} using chunked streaming (-T)...", flush=True)
    up_cmd = [
        'curl.exe', '--http1.1',
        '-H', f'Authorization: token {token}',
        '-H', 'Content-Type: application/octet-stream',
        '-H', 'User-Agent: ReleaseUploader',
        '-T', source_exe,
        upload_url
    ]
    up_res = subprocess.run(up_cmd, capture_output=True, text=True)
    try:
        data = json.loads(up_res.stdout)
        if 'browser_download_url' in data and data.get('state') == 'uploaded':
            print(f"[SUCCESS] {asset_name} uploaded! Size: {data.get('size')} bytes", flush=True)
            print(f"          Download URL: {data['browser_download_url']}", flush=True)
        else:
            print(f"[RESPONSE] {up_res.stdout[:250]}", flush=True)
    except Exception as e:
        print(f"[ERROR] Could not parse upload response: {e}\nRaw output: {up_res.stdout[:300]}", flush=True)

print("\n[GITHUB] All target assets processed!", flush=True)
