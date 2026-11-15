"""Create local secret configuration without displaying or overwriting it."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / '.env'
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('Existing .env preserved; ensure its token is at least 32 characters.')
else:
    with os.fdopen(fd, 'w') as f:
        f.write('HYDRA_TOKEN=' + secrets.token_hex(32) + '\n')
        f.write('HYDRA_URL=http://127.0.0.1:18443\nHYDRA_GRAPH=default\nHYDRA_CELL=cell-0\nHYDRA_NAMESPACE=default\n')
    print('Created private .env with a random token. Token not displayed.')
