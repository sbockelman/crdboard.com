from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from .auth import AccessTokenCodec
from .config import TABLE_ACCESS_SECRET, TABLE_DB_DIR
from .table_state import TableStateStore


def create_table_server_app() -> tuple[Flask, SocketIO]:
    table_id = int(os.getenv("CRDBOARD_TABLE_ID", "1"))
    db_dir = Path(os.getenv("CRDBOARD_TABLE_DB_DIR", str(TABLE_DB_DIR)))
    db_path = db_dir / f"table_{table_id}.sqlite"
    token_codec = AccessTokenCodec(os.getenv("CRDBOARD_TABLE_ACCESS_SECRET", TABLE_ACCESS_SECRET))
    state_store = TableStateStore(db_path)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("CRDBOARD_TABLE_SERVER_SECRET_KEY", "crdboard-dev-table-server-secret")
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    room_name = f"table-{table_id}"
    sid_users: dict[str, dict[str, Any]] = {}
    presence: dict[int, dict[str, Any]] = {}
    user_sids: dict[int, set[str]] = defaultdict(set)
    presence_lock = Lock()

    @app.get("/health")
    def health():
        return {"ok": True, "tableId": table_id}

    @app.get("/state")
    def state():
        return {
            "tableId": table_id,
            "lastEventSeq": state_store.get_last_event_seq(),
            "objects": state_store.get_state(),
        }

    @socketio.on("connect")
    def connect(auth):
        token = None
        if isinstance(auth, dict):
            token = auth.get("token")
        if not token:
            token = request.args.get("token")
        if not token:
            return False
        try:
            claims = token_codec.decode(token)
        except ValueError:
            return False
        if int(claims.get("table_id", -1)) != table_id:
            return False
        user = {"id": int(claims["user_id"]), "username": claims["username"]}
        sid = request.sid
        with presence_lock:
            sid_users[sid] = user
            user_sids[user["id"]].add(sid)
            presence[user["id"]] = user
            presence_snapshot = list(presence.values())

        join_room(room_name)
        requested_seq = 0
        if isinstance(auth, dict):
            requested_seq = int(auth.get("lastEventSeq", 0) or 0)
        snapshot = state_store.get_latest_snapshot()
        if snapshot and requested_seq < snapshot["eventSeq"]:
            requested_seq = snapshot["eventSeq"]
        emit(
            "state_sync",
            {
                "tableId": table_id,
                "snapshot": snapshot["state"] if snapshot else state_store.get_state(),
                "snapshotEventSeq": snapshot["eventSeq"] if snapshot else 0,
                "events": state_store.get_events_since(requested_seq),
                "presence": presence_snapshot,
                "lastEventSeq": state_store.get_last_event_seq(),
            },
        )
        emit("presence_update", {"presence": presence_snapshot}, to=room_name)

    @socketio.on("disconnect")
    def disconnect():
        sid = request.sid
        with presence_lock:
            user = sid_users.pop(sid, None)
            if not user:
                return
            user_sids[user["id"]].discard(sid)
            if not user_sids[user["id"]]:
                user_sids.pop(user["id"], None)
                presence.pop(user["id"], None)
            presence_snapshot = list(presence.values())
        leave_room(room_name)
        emit("presence_update", {"presence": presence_snapshot}, to=room_name)

    @socketio.on("operation")
    def operation(message):
        sid = request.sid
        with presence_lock:
            user = sid_users.get(sid)
        if not user:
            emit("operation_ack", {"ok": False, "error": "Unauthorized"})
            return
        operation_type = str(message.get("type", "")).strip()
        payload = message.get("payload", {})
        client_op_id = message.get("clientOpId")
        try:
            result = state_store.apply_operation(operation_type, payload, user["id"])
            state_store.maybe_snapshot()
        except Exception as exc:  # noqa: BLE001
            emit("operation_ack", {"ok": False, "error": str(exc), "clientOpId": client_op_id})
            return

        event = {
            "seq": result.event_seq,
            "eventType": "object.operation",
            "payload": {
                "objectId": result.object_id,
                "operationType": operation_type,
                "state": result.state,
            },
            "actorUserId": user["id"],
        }
        emit("operation_ack", {"ok": True, "event": event, "clientOpId": client_op_id})
        emit("state_event", event, to=room_name, skip_sid=request.sid)

    return app, socketio


app, socketio = create_table_server_app()


if __name__ == "__main__":
    app_env = os.getenv("CRDBOARD_ENV", "development").lower()
    socketio.run(
        app,
        host="0.0.0.0",
        port=7000,
        debug=os.getenv("FLASK_DEBUG") == "1",
        allow_unsafe_werkzeug=app_env == "production",
    )
