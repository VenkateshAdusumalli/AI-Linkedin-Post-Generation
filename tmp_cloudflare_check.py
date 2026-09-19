import os, json
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE_DIR = Path('.').resolve()
load_dotenv(BASE_DIR / '.env')
account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
token = os.getenv('CLOUDFLARE_API_TOKEN')
print('account', account_id is not None, 'token', token is not None)
model = '@cf/black-forest-labs/flux-1-schnell'
endpoint = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
payload = {
    'prompt': 'Wordless premium professional LinkedIn visual, completely text-free. LinkedIn post theme: AI automation',
}
resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
print(resp.status_code)
print('content-type:', resp.headers.get('Content-Type'))
print(resp.text[:500] if not (resp.headers.get('Content-Type') or '').startswith('image/') else f'<{len(resp.content)} bytes of image data>')
