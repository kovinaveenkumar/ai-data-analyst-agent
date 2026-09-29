import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MCP_MODE"] = "inprocess"  # tests talk to the MCP server in-process


def _db_available() -> bool:
    try:
        from analyst import db

        return db.ping()
    except Exception:  # noqa: BLE001
        return False


DB_UP = _db_available()
needs_db = pytest.mark.skipif(not DB_UP, reason="PostgreSQL not reachable (run: docker compose up -d postgres)")
