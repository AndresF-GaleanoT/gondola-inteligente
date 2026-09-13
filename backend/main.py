# BACKEND / main - expone la FastAPI de app/interfaces/api.py para
# `uvicorn main:app --port 8000`.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.interfaces.api import app  # noqa: E402
