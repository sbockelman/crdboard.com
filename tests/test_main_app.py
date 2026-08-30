from __future__ import annotations

from pathlib import Path

from crdboard.main_app import create_main_app


def test_register_create_table_invite_accept(tmp_path: Path):
    app = create_main_app(data_dir=Path(tmp_path))
    client1 = app.test_client()

    res = client1.post("/api/register", json={"username": "alice", "password": "pw"})
    assert res.status_code == 200
    table_res = client1.post("/api/tables", json={"name": "Session One"})
    assert table_res.status_code == 200
    table_id = table_res.get_json()["table"]["id"]

    invite_res = client1.post(f"/api/tables/{table_id}/invites")
    assert invite_res.status_code == 200
    token = invite_res.get_json()["inviteToken"]

    client2 = app.test_client()
    reg2 = client2.post("/api/register", json={"username": "bob", "password": "pw"})
    assert reg2.status_code == 200
    accept_res = client2.post(f"/api/invites/{token}/accept")
    assert accept_res.status_code == 200

    client3 = app.test_client()
    reg3 = client3.post("/api/register", json={"username": "charlie", "password": "pw"})
    assert reg3.status_code == 200
    second_accept = client3.post(f"/api/invites/{token}/accept")
    assert second_accept.status_code == 400
    assert second_accept.get_json()["error"] == "invite invalid or expired"

    list_res = client2.get("/api/tables")
    assert list_res.status_code == 200
    ids = [t["id"] for t in list_res.get_json()["tables"]]
    assert table_id in ids

    connect_res = client2.get(f"/api/tables/{table_id}/connect")
    assert connect_res.status_code == 200
    assert connect_res.get_json()["accessToken"]
