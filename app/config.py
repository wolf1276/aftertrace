import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Local development convenience; real environment variables always win.
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key, value)
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)


def connect():
    from hydra import Hydra
    return Hydra(os.getenv('HYDRA_URL', 'http://127.0.0.1:18443'),
                 os.environ['HYDRA_TOKEN'], os.getenv('HYDRA_GRAPH', 'default'),
                 os.getenv('HYDRA_CELL', 'cell-0'),
                 namespace=os.getenv('HYDRA_NAMESPACE', 'default'))
