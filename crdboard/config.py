from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(os.getenv("CRDBOARD_BASE_DIR", Path.cwd()))
DATA_DIR = Path(os.getenv("CRDBOARD_DATA_DIR", BASE_DIR / "data"))
MAIN_DB_PATH = DATA_DIR / "main.sqlite"
TABLE_DB_DIR = DATA_DIR / "tables"

APP_ENV = os.getenv("CRDBOARD_ENV", "development").lower()
SECRET_KEY = os.getenv("CRDBOARD_SECRET_KEY")
TABLE_ACCESS_SECRET = os.getenv("CRDBOARD_TABLE_ACCESS_SECRET")

if APP_ENV == "production" and (not SECRET_KEY or not TABLE_ACCESS_SECRET):
    raise RuntimeError("CRDBOARD_SECRET_KEY and CRDBOARD_TABLE_ACCESS_SECRET are required in production")

SECRET_KEY = SECRET_KEY or "crdboard-dev-secret-change-me"
TABLE_ACCESS_SECRET = TABLE_ACCESS_SECRET or "crdboard-dev-table-access-secret-change-me"

TABLE_SERVER_HOST = os.getenv("CRDBOARD_TABLE_SERVER_HOST", "127.0.0.1")
TABLE_SERVER_PUBLIC_HOST = os.getenv("CRDBOARD_TABLE_SERVER_PUBLIC_HOST", TABLE_SERVER_HOST)
TABLE_SERVER_BASE_PORT = int(os.getenv("CRDBOARD_TABLE_SERVER_BASE_PORT", "7000"))
