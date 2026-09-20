"""Audit existing Google auth in CredentialVault."""
import sys, os, keyring
sys.stdout.reconfigure(encoding='utf-8')

service = 'kio_credential_vault'

print('=== Keyring Check ===')
for provider in ['google', 'google_calendar', 'google_drive', 'youtube', 'youtube_data']:
    for ctype in ['oauth2', 'api_key', 'token', 'client']:
        credential_id = f'{provider}_{ctype}'
        secret = keyring.get_password(service, credential_id)
        if secret:
            print(f'  FOUND: {credential_id} (length={len(secret)})')

kio_dir = os.path.expanduser('~/.kio')
print(f'\n=== ~/.kio directory ===')
if os.path.exists(kio_dir):
    for item in sorted(os.listdir(kio_dir)):
        full = os.path.join(kio_dir, item)
        if os.path.isdir(full):
            files = os.listdir(full)
            print(f'  {item}/ ({len(files)} items): {files[:10]}')
        else:
            print(f'  {item} ({os.path.getsize(full)} bytes)')

print('\n=== CredentialVault Check ===')
from mini_kio.core.credential_vault import get_credential_vault
vault = get_credential_vault()
creds = vault.list()
print(f'  Total credentials stored: {len(creds)}')
for c in creds:
    pid = getattr(c, "provider", "?")
    ct = getattr(c, "credential_type", "?")
    cid = getattr(c, "credential_id", "?")[:20]
    print(f'  - provider={pid}, type={ct}, id={cid}...')
