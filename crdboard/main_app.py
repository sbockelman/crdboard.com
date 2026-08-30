from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import AccessTokenCodec
from .config import (
    DATA_DIR,
    MAIN_DB_PATH,
    SECRET_KEY,
    TABLE_ACCESS_SECRET,
    TABLE_SERVER_BASE_PORT,
    TABLE_SERVER_HOST,
)
from .main_db import MainRepository
from .table_manager import TableServerCoordinator


def create_main_app(data_dir: Path | None = None) -> Flask:
    data_dir = data_dir or DATA_DIR
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "templates"),
        static_folder=str(Path(__file__).parent.parent / "static"),
    )
    app.config["SECRET_KEY"] = SECRET_KEY

    repository = MainRepository(data_dir / MAIN_DB_PATH.name)
    coordinator = TableServerCoordinator(repository, TABLE_SERVER_HOST, TABLE_SERVER_BASE_PORT)
    token_codec = AccessTokenCodec(TABLE_ACCESS_SECRET)

    def current_user() -> dict[str, Any] | None:
        user_id = session.get("user_id")
        if not user_id:
            return None
        row = repository.get_user(int(user_id))
        if not row:
            return None
        return {"id": int(row["id"]), "username": row["username"]}

    def login_required(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user():
                return jsonify({"error": "Unauthorized"}), 401
            return func(*args, **kwargs)

        return wrapper

    @app.get("/")
    def index():
        if current_user():
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.get("/dashboard")
    def dashboard():
        if not current_user():
            return redirect(url_for("index"))
        return render_template("dashboard.html")

    @app.get("/tables/<int:table_id>")
    def table_view(table_id: int):
        user = current_user()
        if not user:
            return redirect(url_for("index"))
        if not repository.get_membership(table_id, user["id"]):
            return "Forbidden", 403
        return render_template("table.html", table_id=table_id)

    @app.post("/api/register")
    def register():
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not username or not password:
            return jsonify({"error": "username and password are required"}), 400
        if repository.get_user_by_username(username):
            return jsonify({"error": "username already exists"}), 409
        user_id = repository.create_user(username, generate_password_hash(password))
        session["user_id"] = user_id
        return jsonify({"user": {"id": user_id, "username": username}})

    @app.post("/api/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        user = repository.get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid credentials"}), 401
        session["user_id"] = int(user["id"])
        return jsonify({"user": {"id": int(user["id"]), "username": user["username"]}})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/me")
    def me():
        user = current_user()
        if not user:
            return jsonify({"user": None})
        return jsonify({"user": user})

    @app.get("/api/tables")
    @login_required
    def list_tables():
        user = current_user()
        assert user
        return jsonify({"tables": repository.list_tables_for_user(user["id"])})

    @app.post("/api/tables")
    @login_required
    def create_table():
        user = current_user()
        assert user
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip() or "Untitled Table"
        table_id = repository.create_table(name, user["id"])
        assignment = coordinator.assign(table_id)
        return jsonify(
            {
                "table": {"id": table_id, "name": name},
                "tableServer": {
                    "host": assignment.host,
                    "port": assignment.port,
                    "status": assignment.status,
                    "containerName": assignment.container_name,
                },
            }
        )

    @app.post("/api/tables/<int:table_id>/invites")
    @login_required
    def create_invite(table_id: int):
        user = current_user()
        assert user
        membership = repository.get_membership(table_id, user["id"])
        if not membership:
            return jsonify({"error": "Forbidden"}), 403
        token = repository.create_invite(table_id, user["id"])
        return jsonify({"inviteToken": token, "joinPath": f"/invite/{token}"})

    @app.post("/api/invites/<token>/accept")
    @login_required
    def accept_invite(token: str):
        user = current_user()
        assert user
        invite = repository.get_invite(token)
        if not invite:
            return jsonify({"error": "invite not found"}), 404
        table_id = repository.accept_invite(token, user["id"])
        coordinator.assign(table_id)
        return jsonify({"tableId": table_id})

    @app.get("/api/tables/<int:table_id>/connect")
    @login_required
    def get_table_connection(table_id: int):
        user = current_user()
        assert user
        if not repository.get_membership(table_id, user["id"]):
            return jsonify({"error": "Forbidden"}), 403
        assignment = coordinator.assign(table_id)
        token = token_codec.encode(
            {
                "table_id": table_id,
                "user_id": user["id"],
                "username": user["username"],
            }
        )
        return jsonify(
            {
                "tableId": table_id,
                "socketUrl": assignment.ws_url,
                "accessToken": token,
                "serverStatus": assignment.status,
                "containerName": assignment.container_name,
            }
        )

    @app.get("/api/tables/<int:table_id>/orchestration")
    @login_required
    def orchestration_hint(table_id: int):
        user = current_user()
        assert user
        if not repository.get_membership(table_id, user["id"]):
            return jsonify({"error": "Forbidden"}), 403
        assignment = coordinator.assign(table_id)
        hint = {
            "tableId": table_id,
            "containerName": assignment.container_name,
            "recommendedCommand": (
                "docker run -d "
                f"--name {assignment.container_name} "
                f"-e CRDBOARD_TABLE_ID={table_id} "
                f"-e CRDBOARD_TABLE_ACCESS_SECRET={TABLE_ACCESS_SECRET} "
                f"-p {assignment.port}:7000 crdboard-table-server"
            ),
        }
        return jsonify(hint)

    return app


app = create_main_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
