"""backend 루트를 import 경로에 넣는다. `pytest`를 backend/ 밖에서 실행해도 되게."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
