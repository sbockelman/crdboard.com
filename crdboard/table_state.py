from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class OperationResult:
    object_id: str
    event_seq: int
    operation_type: str
    state: dict[str, Any]


class TableStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS object_state (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    rotation REAL NOT NULL,
                    face TEXT NOT NULL,
                    z_index INTEGER NOT NULL,
                    stack_id TEXT,
                    stack_order INTEGER,
                    metadata_json TEXT NOT NULL,
                    edit_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS object_revisions (
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    operation_payload_json TEXT NOT NULL,
                    actor_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    actor_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_seq INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _serialize_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "sourceType": row["source_type"],
            "sourceId": row["source_id"],
            "ownerUserId": row["owner_user_id"],
            "position": {"x": row["position_x"], "y": row["position_y"]},
            "rotation": row["rotation"],
            "face": row["face"],
            "zIndex": row["z_index"],
            "stackId": row["stack_id"],
            "stackOrder": row["stack_order"],
            "metadata": json.loads(row["metadata_json"]),
            "editPayload": json.loads(row["edit_payload_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def get_state(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM object_state WHERE deleted = 0 ORDER BY z_index ASC, id ASC"
            ).fetchall()
            return [self._serialize_row(row) for row in rows]

    def get_last_event_seq(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM events").fetchone()
            return int(row["seq"])

    def get_events_since(self, seq: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT seq, event_type, payload_json, actor_user_id, created_at FROM events WHERE seq > ? ORDER BY seq ASC",
                (seq,),
            ).fetchall()
            return [
                {
                    "seq": int(row["seq"]),
                    "eventType": row["event_type"],
                    "payload": json.loads(row["payload_json"]),
                    "actorUserId": int(row["actor_user_id"]),
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    def get_latest_snapshot(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT snapshot_id, event_seq, state_json, created_at FROM snapshots ORDER BY snapshot_id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return {
                "snapshotId": int(row["snapshot_id"]),
                "eventSeq": int(row["event_seq"]),
                "state": json.loads(row["state_json"]),
                "createdAt": row["created_at"],
            }

    def _record_event(self, conn: sqlite3.Connection, event_type: str, payload: dict[str, Any], actor_user_id: int) -> int:
        cur = conn.execute(
            """
            INSERT INTO events(event_type, payload_json, actor_user_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, json.dumps(payload), actor_user_id, utcnow()),
        )
        return int(cur.lastrowid)

    def _record_revision(
        self, conn: sqlite3.Connection, object_id: str, operation_type: str, payload: dict[str, Any], actor_user_id: int
    ) -> None:
        conn.execute(
            """
            INSERT INTO object_revisions(object_id, operation_type, operation_payload_json, actor_user_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (object_id, operation_type, json.dumps(payload), actor_user_id, utcnow()),
        )

    def maybe_snapshot(self, every_n_events: int = 25) -> None:
        with self._lock:
            with self._conn() as conn:
                last_snapshot_seq = conn.execute(
                    "SELECT COALESCE(MAX(event_seq), 0) as seq FROM snapshots"
                ).fetchone()["seq"]
                max_seq = conn.execute("SELECT COALESCE(MAX(seq), 0) as seq FROM events").fetchone()["seq"]
                if int(max_seq) - int(last_snapshot_seq) < every_n_events:
                    return
                rows = conn.execute(
                    "SELECT * FROM object_state WHERE deleted = 0 ORDER BY z_index ASC, id ASC"
                ).fetchall()
                state = [self._serialize_row(row) for row in rows]
                conn.execute(
                    "INSERT INTO snapshots(event_seq, state_json, created_at) VALUES (?, ?, ?)",
                    (max_seq, json.dumps(state), utcnow()),
                )

    def apply_operation(self, operation_type: str, payload: dict[str, Any], actor_user_id: int) -> OperationResult:
        with self._lock:
            with self._conn() as conn:
                if operation_type == "print_object":
                    result = self._op_print_object(conn, payload, actor_user_id)
                elif operation_type in {"move", "rotate", "flip", "edit", "set_z", "stack"}:
                    result = self._op_update_object(conn, operation_type, payload, actor_user_id)
                else:
                    raise ValueError(f"Unsupported operation: {operation_type}")
                self._record_revision(conn, result.object_id, operation_type, payload, actor_user_id)
                event_payload = {
                    "objectId": result.object_id,
                    "operationType": operation_type,
                    "state": result.state,
                }
                event_seq = self._record_event(conn, "object.operation", event_payload, actor_user_id)
                result.event_seq = event_seq
                return result

    def _next_z_index(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COALESCE(MAX(z_index), 0) AS z FROM object_state WHERE deleted = 0").fetchone()
        return int(row["z"]) + 1

    def _op_print_object(self, conn: sqlite3.Connection, payload: dict[str, Any], actor_user_id: int) -> OperationResult:
        source = payload.get("source", {})
        source_type = str(source.get("type", "card"))
        source_id = str(source.get("id", "unknown"))
        obj_id = payload.get("objectId") or uuid4().hex
        position = payload.get("position", {"x": 0, "y": 0})
        metadata = payload.get("metadata", {})
        edit_payload = payload.get("editPayload", {})
        now = utcnow()
        z_index = payload.get("zIndex", self._next_z_index(conn))
        face = payload.get("face", "front")
        conn.execute(
            """
            INSERT INTO object_state(
                id, source_type, source_id, owner_user_id, position_x, position_y, rotation, face,
                z_index, stack_id, stack_order, metadata_json, edit_payload_json, created_at, updated_at, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                obj_id,
                source_type,
                source_id,
                actor_user_id,
                float(position.get("x", 0)),
                float(position.get("y", 0)),
                float(payload.get("rotation", 0)),
                face,
                int(z_index),
                payload.get("stackId"),
                payload.get("stackOrder"),
                json.dumps(metadata),
                json.dumps(edit_payload),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM object_state WHERE id = ?", (obj_id,)).fetchone()
        return OperationResult(obj_id, 0, "print_object", self._serialize_row(row))

    def _load_object(self, conn: sqlite3.Connection, object_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM object_state WHERE id = ? AND deleted = 0",
            (object_id,),
        ).fetchone()
        if not row:
            raise ValueError("Object not found")
        return row

    def _op_update_object(
        self, conn: sqlite3.Connection, operation_type: str, payload: dict[str, Any], actor_user_id: int
    ) -> OperationResult:
        object_id = str(payload["objectId"])
        row = self._load_object(conn, object_id)

        position_x = float(row["position_x"])
        position_y = float(row["position_y"])
        rotation = float(row["rotation"])
        face = row["face"]
        z_index = int(row["z_index"])
        stack_id = row["stack_id"]
        stack_order = row["stack_order"]
        metadata = json.loads(row["metadata_json"])
        edit_payload = json.loads(row["edit_payload_json"])

        if operation_type == "move":
            pos = payload.get("position", {})
            position_x = float(pos.get("x", position_x))
            position_y = float(pos.get("y", position_y))
        elif operation_type == "rotate":
            rotation = float(payload.get("rotation", rotation))
        elif operation_type == "flip":
            face = "back" if face == "front" else "front"
        elif operation_type == "set_z":
            z_index = int(payload.get("zIndex", z_index))
        elif operation_type == "edit":
            edit_payload.update(payload.get("editPayload", {}))
            metadata.update(payload.get("metadata", {}))
        elif operation_type == "stack":
            stack_id = payload.get("stackId")
            stack_order = payload.get("stackOrder")
            z_index = int(payload.get("zIndex", z_index))

        conn.execute(
            """
            UPDATE object_state SET
                position_x = ?, position_y = ?, rotation = ?, face = ?, z_index = ?,
                stack_id = ?, stack_order = ?, metadata_json = ?, edit_payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                position_x,
                position_y,
                rotation,
                face,
                z_index,
                stack_id,
                stack_order,
                json.dumps(metadata),
                json.dumps(edit_payload),
                utcnow(),
                object_id,
            ),
        )
        updated_row = conn.execute("SELECT * FROM object_state WHERE id = ?", (object_id,)).fetchone()
        return OperationResult(object_id, 0, operation_type, self._serialize_row(updated_row))
