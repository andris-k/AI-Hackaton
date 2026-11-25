"""The counting workspace: statuses, exact counts, "not found here", search and the review."""

from __future__ import annotations

import pytest

from app import db
from app.repositories import audit_repository
from app.services import counting_workspace_service as workspace


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()
    audit_repository.initialize_audit_storage()


@pytest.fixture
def rooms() -> tuple[str, str]:
    return str(db.create_location("Room A")["id"]), str(db.create_location("Room B")["id"])


def _asset(name: str, quantity: int = 2, location_id: str | None = None, category: str = "Furniture") -> str:
    category_id = db.create_fixed_asset_category(category)["id"]
    return str(db.create_fixed_asset(
        name=name, category_id=category_id, quantity=quantity, initial_value=10.0,
        responsible_person="Jane", registration_date="2026-01-01", location_id=location_id,
    )["id"])


def _active_session(location_id: str | None, linked: list[tuple[str, int]]) -> str:
    session_id = str(db.create_inventory_session(
        date_from="2026-12-01", date_to="2026-12-31", responsible_person="Jane", location_id=location_id,
    )["id"])
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status="Active",
        responsible_person="Jane", linked_assets=linked,
    )
    return session_id


def _rows(session_id: str) -> dict[str, dict]:
    return {row["name"]: row for row in workspace.build_rows(db.get_inventory_session_by_id(session_id))}


@pytest.mark.parametrize(
    "expected, total, has_counts, key, label",
    [
        (3, 0, False, "todo", "Not counted yet"),
        (3, 3, True, "matched", "Matched"),
        (3, 0, True, "notfound", "Not found"),
        (3, 5, True, "extra", "Extra +2"),
        (3, 1, True, "missing", "Missing −2"),
        (0, 0, True, "matched", "Matched"),
    ],
)
def test_asset_status(expected, total, has_counts, key, label):
    assert workspace.asset_status(expected, total, has_counts) == (key, label)


def test_exact_count_and_not_found_here(rooms):
    room_a, room_b = rooms
    chair = _asset("Chair", 5, room_a)
    desk = _asset("Desk", 1, room_b)
    session_id = _active_session(room_a, [(chair, 0), (desk, 0)])

    outcome = db.adjust_inventory_count(session_id, chair, None, quantity=4)
    assert (outcome["result"], outcome["quantity"], outcome["here_quantity"]) == ("counted", 4, 4)

    # 0 without "not found" leaves the asset not counted; with it, it is not found.
    db.adjust_inventory_count(session_id, desk, None, quantity=0)
    assert _rows(session_id)["Desk"]["status_key"] == "todo"
    db.adjust_inventory_count(session_id, desk, None, quantity=0, keep_zero=True)
    rows = _rows(session_id)
    assert (rows["Desk"]["status_key"], rows["Desk"]["counted_at"]) == ("notfound", "Not found at Room A")
    assert (rows["Chair"]["status_key"], rows["Chair"]["status_label"]) == ("missing", "Missing −1")


def test_rows_show_counts_per_location_and_where_assets_belong(rooms):
    room_a, room_b = rooms
    chair = _asset("Chair", 5, room_a)
    desk = _asset("Desk", 1, room_b)
    lamp = _asset("Lamp", 1, room_b)
    session_id = _active_session(room_a, [(chair, 3), (desk, 0), (lamp, 0)])
    db.set_active_location(session_id, room_b, None)
    db.adjust_inventory_count(session_id, chair, 2)
    db.adjust_inventory_count(session_id, desk, 1)

    rows = workspace.build_rows(db.get_inventory_session_by_id(session_id))

    assert [r["name"] for r in rows] == ["Desk", "Lamp", "Chair"]  # registered at Room B first
    chair_row = rows[2]
    assert (chair_row["here"], chair_row["total"], chair_row["status_key"]) == (2, 5, "matched")
    assert chair_row["counted_at"] == "Counted at Room A: 3 · Room B: 2"
    assert chair_row["found_away"] is True and chair_row["at_location"] is False
    summary = workspace.summary(rows)
    assert {k: summary[k] for k in ("matched", "differ", "todo", "total")} == {
        "matched": 2, "differ": 0, "todo": 1, "total": 3}
    assert (summary["registered_here"], summary["done_here"], summary["found_away"]) == (2, 1, 1)


def test_review_lists_not_counted_and_differences(rooms):
    room_a, _ = rooms
    chair = _asset("Chair", 5, room_a)
    desk = _asset("Desk", 1, room_a)
    lamp = _asset("Lamp", 1, room_a)
    session_id = _active_session(room_a, [(chair, 4), (desk, 1), (lamp, 0)])

    review = workspace.build_review(db.get_inventory_session_by_id(session_id))

    assert [r["name"] for r in review["not_counted"]] == ["Lamp"]
    assert [r["name"] for r in review["differences"]] == ["Chair"]
    assert review["summary"]["matched"] == 1


def test_remove_asset_from_session(rooms):
    chair = _asset("Chair", 1, rooms[0])
    session_id = _active_session(rooms[0], [(chair, 1)])

    assert db.remove_asset_from_session(session_id, chair)["result"] == "removed"
    assert db.remove_asset_from_session(session_id, chair)["result"] == "not_linked"
    assert db.list_session_counts(session_id) == []
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status="Completed",
        responsible_person="Jane",
    )
    assert db.remove_asset_from_session(session_id, chair)["result"] == "closed"


def test_search_assets(rooms):
    chair = _asset("Office chair", 1, rooms[0])
    _asset("Desk chair", 1, rooms[0])
    _asset("Laptop", 1, category="IT equipment")
    db.delete_fixed_asset(_asset("Old chair"))
    session_id = _active_session(rooms[0], [(chair, 1)])

    names = [(row["name"], bool(row["in_session"])) for row in db.search_assets_for_session(session_id, "chair")]
    assert names == [("Desk chair", False), ("Office chair", True)]
    assert [row["name"] for row in db.search_assets_for_session(session_id, "it equip")] == ["Laptop"]
    assert [row["name"] for row in db.search_assets_for_session(session_id, chair[:6])] == ["Office chair"]
    assert db.search_assets_for_session(session_id, "  ") == []


def test_recent_counts_read_the_audit_log():
    record = audit_repository.record_event
    record("inventory_session.count_changed", "anna@example.com", None,
           {"session_id": "s1", "name": "Chair", "delta": 1, "location": "Room A"})
    record("inventory_session.count_changed", "anna@example.com", None,
           {"session_id": "s1", "name": "Desk", "set_to": 0, "not_found": True, "location": "Room A"})
    record("inventory_session.location_changed", "anna@example.com", None,
           {"session_id": "s1", "changes": {"location": ["Room A", "Room B"]}})
    record("inventory_session.updated", "anna@example.com", None, {"session_id": "s1"})

    lines = [line["what"] for line in workspace.recent_counts("s1")]

    assert lines == ["Switched to Room B", "Desk: not found at Room A", "Chair: +1 at Room A"]


def test_status_changes_through_the_repository_keep_assets(rooms):
    """The Start, Complete and Cancel routes call the repository without assets."""
    from app.repositories import inventory_sessions_repository as repo

    chair = _asset("Chair", 2, rooms[0])
    session_id = _active_session(rooms[0], [(chair, 2)])
    for status in ("Active", "Completed"):
        repo.update_session(
            session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status=status,
            responsible_person="Jane",
        )
    assert [(row["name"], row["quantity"]) for row in repo.list_linked_assets(session_id)] == [("Chair", 2)]


def test_undo_puts_a_removed_asset_back_with_its_counts(rooms):
    room_a, room_b = rooms
    chair = _asset("Chair", 5, room_a)
    desk = _asset("Desk", 1, room_a)
    session_id = _active_session(room_a, [(chair, 3), (desk, 0)])
    db.adjust_inventory_count(session_id, desk, None, quantity=0, keep_zero=True)
    db.set_active_location(session_id, room_b, None)
    db.adjust_inventory_count(session_id, chair, 2)
    before = _rows(session_id)

    removed = db.remove_asset_from_session(session_id, chair)
    removed_desk = db.remove_asset_from_session(session_id, desk)
    assert sorted(removed["counts"], key=str) == sorted([[room_a, 3], [room_b, 2]], key=str)
    assert set(_rows(session_id)) == set()

    assert db.restore_asset_to_session(session_id, chair, removed["counts"]) == "restored"
    assert db.restore_asset_to_session(session_id, desk, removed_desk["counts"]) == "restored"
    after = _rows(session_id)
    for name in ("Chair", "Desk"):
        keys = ("expected", "total", "here", "counted_at", "status_key")
        assert {k: after[name][k] for k in keys} == {k: before[name][k] for k in keys}
    assert db.restore_asset_to_session(session_id, chair, removed["counts"]) == "already_in_session"


def test_undo_takes_the_expected_quantity_from_the_asset(rooms):
    chair = _asset("Chair", 5, rooms[0])
    session_id = _active_session(rooms[0], [(chair, 1)])
    removed = db.remove_asset_from_session(session_id, chair)

    db.restore_asset_to_session(session_id, chair, removed["counts"])

    assert _rows(session_id)["Chair"]["expected"] == 5  # not something sent by the browser


def test_undo_is_refused_once_the_session_is_closed(rooms):
    chair = _asset("Chair", 1, rooms[0])
    session_id = _active_session(rooms[0], [(chair, 1)])
    removed = db.remove_asset_from_session(session_id, chair)
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status="Completed",
        responsible_person="Jane",
    )
    assert db.restore_asset_to_session(session_id, chair, removed["counts"]) == "closed"
