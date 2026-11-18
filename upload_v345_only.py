import subprocess
import json
import os
import sys
import time

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    creds, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    return dict([l.split('=', 1) for l in creds.splitlines() if '=' in l]).get('password', '')

token = get_token()
repo = "sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE"
source_file = r"L:\ClipifyAI\Clipify Setup 3.4.5.exe"
file_size = os.path.getsize(source_file)
print(f"File size to upload: {file_size / (1024*1024):.2f} MB")

rel_id = 450166488
tag = "v3.4.5"
asset_name = "Clipify.Setup.3.4.5.exe"

# 1. Delete if existing
chk_cmd = [
    'curl.exe', '-s',
    '-H', f'Authorization: token {token}',
    '-H', 'User-Agent: ReleaseUploader',
    f'https://api.github.com/repos/{repo}/releases/{rel_id}/assets'
]
res = subprocess.run(chk_cmd, capture_output=True, text=True)
try:
    assets = json.loads(res.stdout)
    for a in assets:
        if a.get('name') == asset_name:
            print(f"Deleting asset {asset_name} (id: {a['id']})...")
            del_cmd = [
                'curl.exe', '-s', '-X', 'DELETE',
                '-H', f'Authorization: token {token}',
                '-H', 'User-Agent: ReleaseUploader',
                f'https://api.github.com/repos/{repo}/releases/assets/{a["id"]}'
            ]
            subprocess.run(del_cmd, capture_output=True)
except Exception as e:
    print("Asset check error:", e)

# 2. Upload with retry
upload_url = f"https://uploads.github.com/repos/{repo}/releases/{rel_id}/assets?name={asset_name}"
for attempt in range(1, 4):
    print(f"Attempt {attempt}/3 uploading {asset_name}...")
    up_cmd = [
        'curl.exe', '--http1.1',
        '-H', f'Authorization: token {token}',
        '-H', 'Content-Type: application/octet-stream',
        '-H', 'User-Agent: ReleaseUploader',
        '--speed-time', '30',
        '--speed-limit', '1000',
        '-T', source_file,
        upload_url
    ]
    up_res = subprocess.run(up_cmd, capture_output=True, text=True)
    try:
        data = json.loads(up_res.stdout)
        if 'browser_download_url' in data:
            print(f"SUCCESS! Download URL: {data['browser_download_url']}")
            sys.exit(0)
        else:
            print(f"Upload response: {up_res.stdout[:200]}")
    except Exception as e:
        print(f"Response parse error: {e}, stdout: {up_res.stdout[:200]}")
    time.sleep(3)

print("Upload failed after 3 attempts")
sys.exit(1)

