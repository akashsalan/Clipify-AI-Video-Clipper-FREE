import subprocess
import json

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    creds, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    return dict([l.split('=', 1) for l in creds.splitlines() if '=' in l]).get('password', '')

token = get_token()
cmd = [
    'curl.exe', '-s',
    '-H', f'Authorization: token {token}',
    '-H', 'User-Agent: ReleaseInspector',
    'https://api.github.com/repos/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE/releases'
]
res = subprocess.run(cmd, capture_output=True, text=True)
try:
    rels = json.loads(res.stdout)
    for r in rels[:5]:
        print(f"TAG: {r['tag_name']} | ID: {r['id']} | Published: {r.get('published_at')} | URL: {r.get('html_url')}")
        for a in r.get('assets', []):
            print(f"    Asset: {a['name']} ({a['size']} bytes) -> {a['browser_download_url']}")
        if not r.get('assets'):
            print("    NO ASSETS!")
except Exception as e:
    print("Error parsing releases:", e)
