import os, json
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE_DIR = Path('.').resolve()
load_dotenv(BASE_DIR / '.env')
account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
token = os.getenv('CLOUDFLARE_API_TOKEN')
print('account', account_id is not None, 'token', token is not None)
endpoint = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/ai/generate'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
payload = {
    'model': '@cf/black-forest-labs/flux-1-schnell',
    'input': 'Generate a simple professional business image from the following text. LinkedIn post: AI automation',
    'modalities': ['image'],
}
resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
print(resp.status_code)
print(resp.text)
