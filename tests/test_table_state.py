from __future__ import annotations

from pathlib import Path

from crdboard.table_state import TableStateStore


def test_print_and_mutate_object(tmp_path: Path):
    store = TableStateStore(tmp_path / "table.sqlite")
    printed = store.apply_operation(
        "print_object",
        {
            "source": {"type": "card", "id": "ace-spades"},
            "position": {"x": 10, "y": 20},
            "metadata": {"label": "Ace"},
        },
        actor_user_id=1,
    )
    obj_id = printed.object_id
    assert printed.state["sourceId"] == "ace-spades"

    moved = store.apply_operation("move", {"objectId": obj_id, "position": {"x": 22, "y": 33}}, actor_user_id=1)
    assert moved.state["position"]["x"] == 22
    assert moved.state["position"]["y"] == 33

    flipped = store.apply_operation("flip", {"objectId": obj_id}, actor_user_id=2)
    assert flipped.state["face"] == "back"

    edited = store.apply_operation(
        "edit",
        {"objectId": obj_id, "editPayload": {"name": "Ace of Spades Foil"}, "metadata": {"rarity": "legendary"}},
        actor_user_id=2,
    )
    assert edited.state["editPayload"]["name"] == "Ace of Spades Foil"
    assert edited.state["metadata"]["rarity"] == "legendary"

    events = store.get_events_since(0)
    assert len(events) == 4
    assert events[-1]["payload"]["operationType"] == "edit"


def test_snapshot_generation(tmp_path: Path):
    store = TableStateStore(tmp_path / "table.sqlite")
    for i in range(3):
        store.apply_operation(
            "print_object",
            {"source": {"type": "card", "id": f"c{i}"}, "position": {"x": i, "y": i}},
            actor_user_id=1,
        )
    store.maybe_snapshot(every_n_events=2)
    snap = store.get_latest_snapshot()
    assert snap is not None
    assert snap["eventSeq"] >= 2
    assert len(snap["state"]) == 3
