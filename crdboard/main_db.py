from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class MainRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(owner_user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS table_memberships (
                    table_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    invited_by INTEGER,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (table_id, user_id),
                    FOREIGN KEY(table_id) REFERENCES tables(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS invites (
                    token TEXT PRIMARY KEY,
                    table_id INTEGER NOT NULL,
                    inviter_user_id INTEGER NOT NULL,
                    accepted_by_user_id INTEGER,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(table_id) REFERENCES tables(id),
                    FOREIGN KEY(inviter_user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS table_server_assignments (
                    table_id INTEGER PRIMARY KEY,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    container_name TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(table_id) REFERENCES tables(id)
                );
                """
            )

    def create_user(self, username: str, password_hash: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, utcnow()),
            )
            return int(cur.lastrowid)

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_table(self, name: str, owner_user_id: int) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tables(name, owner_user_id, created_at) VALUES (?, ?, ?)",
                (name, owner_user_id, utcnow()),
            )
            table_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO table_memberships(table_id, user_id, role, invited_by, created_at)
                VALUES (?, ?, 'owner', ?, ?)
                """,
                (table_id, owner_user_id, owner_user_id, utcnow()),
            )
            return table_id

    def list_tables_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.name, t.owner_user_id, t.status, t.created_at, m.role
                FROM tables t
                JOIN table_memberships m ON m.table_id = t.id
                WHERE m.user_id = ?
                ORDER BY t.id DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_table(self, table_id: int) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM tables WHERE id = ?", (table_id,)).fetchone()

    def get_membership(self, table_id: int, user_id: int) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM table_memberships WHERE table_id = ? AND user_id = ?",
                (table_id, user_id),
            ).fetchone()

    def add_membership(self, table_id: int, user_id: int, role: str, invited_by: int | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO table_memberships(table_id, user_id, role, invited_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (table_id, user_id, role, invited_by, utcnow()),
            )

    def create_invite(self, table_id: int, inviter_user_id: int, ttl_hours: int = 72) -> str:
        token = uuid4().hex
        expires_at = (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO invites(token, table_id, inviter_user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token, table_id, inviter_user_id, expires_at, utcnow()),
            )
        return token

    def get_invite(self, token: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM invites WHERE token = ?", (token,)).fetchone()

    def accept_invite(self, token: str, user_id: int) -> int:
        with self._conn() as conn:
            invite = conn.execute("SELECT * FROM invites WHERE token = ?", (token,)).fetchone()
            if not invite:
                raise ValueError("Invite not found")
            if invite["accepted_by_user_id"]:
                return int(invite["table_id"])
            conn.execute(
                "UPDATE invites SET accepted_by_user_id = ? WHERE token = ?",
                (user_id, token),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO table_memberships(table_id, user_id, role, invited_by, created_at)
                VALUES (?, ?, 'player', ?, ?)
                """,
                (invite["table_id"], user_id, invite["inviter_user_id"], utcnow()),
            )
            return int(invite["table_id"])

    def get_assignment(self, table_id: int) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM table_server_assignments WHERE table_id = ?",
                (table_id,),
            ).fetchone()

    def upsert_assignment(self, table_id: int, host: str, port: int, status: str, container_name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO table_server_assignments(table_id, host, port, status, container_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(table_id) DO UPDATE SET
                    host = excluded.host,
                    port = excluded.port,
                    status = excluded.status,
                    container_name = excluded.container_name,
                    updated_at = excluded.updated_at
                """,
                (table_id, host, port, status, container_name, utcnow()),
            )
