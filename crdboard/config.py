from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(os.getenv("CRDBOARD_BASE_DIR", Path.cwd()))
DATA_DIR = Path(os.getenv("CRDBOARD_DATA_DIR", BASE_DIR / "data"))
MAIN_DB_PATH = DATA_DIR / "main.sqlite"
TABLE_DB_DIR = DATA_DIR / "tables"

SECRET_KEY = os.getenv("CRDBOARD_SECRET_KEY", "dev-secret")
TABLE_ACCESS_SECRET = os.getenv("CRDBOARD_TABLE_ACCESS_SECRET", "table-dev-secret")

TABLE_SERVER_HOST = os.getenv("CRDBOARD_TABLE_SERVER_HOST", "127.0.0.1")
TABLE_SERVER_BASE_PORT = int(os.getenv("CRDBOARD_TABLE_SERVER_BASE_PORT", "7000"))
