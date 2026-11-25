"""Active locations in inventory sessions and counts per location.

These tests run against a throwaway SQLite file so they exercise the real SQL.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.services.inventory_sessions_service import is_stale


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()


@pytest.fixture
def user_id() -> int:
    return int(db.create_user("counter@example.com", "pw")["id"])


@pytest.fixture
def rooms() -> tuple[str, str]:
    return str(db.create_location("Room A")["id"]), str(db.create_location("Room B")["id"])


def _asset(name: str = "Office chair", quantity: int = 5, location_id: str | None = None) -> str:
    category_id = db.create_fixed_asset_category("Furniture")["id"]
    return str(db.create_fixed_asset(
        name=name, category_id=category_id, quantity=quantity, initial_value=10.0,
        responsible_person="Jane", registration_date="2026-01-01", location_id=location_id,
    )["id"])


def _session(location_id: str | None = None, linked: list[tuple[str, int]] | None = None, status: str = "Active") -> str:
    session_id = str(db.create_inventory_session(
        date_from="2026-12-01", date_to="2026-12-31", responsible_person="Jane", location_id=location_id,
    )["id"])
    if status != "New":
        _save(session_id, status, linked)
    return session_id


def _save(session_id: str, status: str = "Active", linked: list[tuple[str, int]] | None = None) -> None:
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status=status,
        responsible_person="Jane", linked_assets=linked,
    )


def _counts(session_id: str) -> dict[tuple[str, str | None], int]:
    return {(str(row["fixed_asset_id"]), row["location"]): int(row["quantity"]) for row in db.list_session_counts(session_id)}


def _total(session_id: str, asset_id: str) -> tuple[int, int]:
    """(expected, counted total)"""
    (row,) = [row for row in db.list_fixed_assets_for_inventory_session(session_id) if row["id"] == asset_id]
    return int(row["expected_quantity"]), int(row["quantity"])


# ---------------------------------------------------------------------------
# Active location and its history (1, 2)
# ---------------------------------------------------------------------------


def test_active_location_can_change_many_times(rooms, user_id):
    room_a, room_b = rooms
    session_id = _session(room_a)

    assert db.set_active_location(session_id, room_b, user_id) == "changed"
    assert db.set_active_location(session_id, room_b, user_id) == "unchanged"
    assert db.set_active_location(session_id, None, user_id) == "changed"
    assert db.set_active_location(session_id, room_a, user_id) == "changed"

    history = [(row["location"], row["activated_by_email"]) for row in db.list_session_location_history(session_id)]
    assert history == [("Room A", None), ("Room B", "counter@example.com"), (None, "counter@example.com"),
                       ("Room A", "counter@example.com")]
    assert db.get_inventory_session_by_id(session_id)["location"] == "Room A"


def test_active_location_only_in_new_and_active_sessions(rooms, user_id):
    room_a, _ = rooms
    new_session = _session(status="New")
    completed = _session(status="Completed")

    assert db.set_active_location(new_session, room_a, user_id) == "changed"
    assert db.set_active_location(completed, room_a, user_id) == "closed"
    assert db.set_active_location("missing", room_a, user_id) == "session_not_found"
    with pytest.raises(ValueError):
        db.set_active_location(new_session, "no-such-location", user_id)


def test_changing_location_makes_open_edit_pages_stale(rooms, user_id):
    session_id = _session(rooms[0])
    loaded = str(db.get_inventory_session_by_id(session_id)["updated_at"])

    db.set_active_location(session_id, rooms[1], user_id)

    assert is_stale(loaded, db.get_inventory_session_by_id(session_id)["updated_at"])


def test_sessions_filter_by_any_location_used(rooms, user_id):
    room_a, room_b = rooms
    moved_on = _session(room_a)
    db.set_active_location(moved_on, room_b, user_id)
    _session(room_b)
    _session()

    assert [row["id"] for row in db.list_inventory_sessions(location_id=room_a)] == [moved_on]
    assert len(db.list_inventory_sessions(location_id=room_b)) == 2


# ---------------------------------------------------------------------------
# Counts per location (3)
# ---------------------------------------------------------------------------


def test_scans_are_counted_at_the_active_location(rooms, user_id):
    room_a, room_b = rooms
    chair = _asset(quantity=5, location_id=room_a)
    session_id = _session(room_a)

    db.adjust_inventory_count(session_id, chair, 1)
    db.adjust_inventory_count(session_id, chair, 1)
    db.set_active_location(session_id, room_b, user_id)
    outcome = db.adjust_inventory_count(session_id, chair, 1)

    assert (outcome["quantity"], outcome["here_quantity"], outcome["location"]) == (3, 1, "Room B")
    assert outcome["other_location"] is True  # registered at Room A, found in Room B
    assert _counts(session_id) == {(chair, "Room A"): 2, (chair, "Room B"): 1}
    assert _total(session_id, chair) == (5, 3)


def test_counting_without_a_location(rooms, user_id):
    chair = _asset()
    session_id = _session()

    db.adjust_inventory_count(session_id, chair, 2)
    db.set_active_location(session_id, rooms[0], user_id)
    db.adjust_inventory_count(session_id, chair, 1)

    assert _counts(session_id) == {(chair, None): 2, (chair, "Room A"): 1}
    assert _total(session_id, chair)[1] == 3


def test_minus_only_takes_away_at_the_active_location(rooms, user_id):
    chair = _asset()
    session_id = _session(rooms[0])
    db.adjust_inventory_count(session_id, chair, 1)
    db.set_active_location(session_id, rooms[1], user_id)

    assert db.adjust_inventory_count(session_id, chair, -1)["result"] == "not_counted_here"
    assert _total(session_id, chair)[1] == 1


def test_edit_page_saves_the_count_at_the_active_location_and_keeps_others(rooms, user_id):
    room_a, room_b = rooms
    chair = _asset(quantity=5)
    desk = _asset("Desk", quantity=1)
    session_id = _session(room_a, linked=[(chair, 3)])
    db.set_active_location(session_id, room_b, user_id)

    _save(session_id, linked=[(chair, 2), (desk, 1)])

    assert _counts(session_id) == {(chair, "Room A"): 3, (chair, "Room B"): 2, (desk, "Room B"): 1}
    assert _total(session_id, chair) == (5, 5)


def test_zero_on_the_edit_page_adds_no_empty_location(rooms, user_id):
    room_a, room_b = rooms
    chair = _asset()
    session_id = _session(room_a, linked=[(chair, 3)])
    db.set_active_location(session_id, room_b, user_id)

    _save(session_id, linked=[(chair, 0)])  # an untouched row at Room B
    assert _counts(session_id) == {(chair, "Room A"): 3}

    db.set_active_location(session_id, room_a, user_id)
    _save(session_id, linked=[(chair, 0)])  # clearing the count at Room A
    assert _counts(session_id) == {(chair, "Room A"): 0}
    assert _total(session_id, chair)[1] == 0


def test_removing_an_asset_removes_its_counts(rooms, user_id):
    chair = _asset()
    desk = _asset("Desk")
    session_id = _session(rooms[0], linked=[(chair, 2), (desk, 1)])

    _save(session_id, linked=[(desk, 1)])

    assert _counts(session_id) == {(desk, "Room A"): 1}


def test_status_changes_keep_counts(rooms, user_id):
    room_a, room_b = rooms
    chair = _asset()
    session_id = _session(room_a, linked=[(chair, 2)])
    db.set_active_location(session_id, room_b, user_id)
    db.adjust_inventory_count(session_id, chair, 1)

    _save(session_id, status="Completed")  # what the Complete button does: no linked assets

    assert _counts(session_id) == {(chair, "Room A"): 2, (chair, "Room B"): 1}
    assert _total(session_id, chair)[1] == 3


def test_counts_at_the_active_location_for_the_edit_page(rooms, user_id):
    chair = _asset()
    session_id = _session(rooms[0], linked=[(chair, 2)])
    db.set_active_location(session_id, rooms[1], user_id)
    db.adjust_inventory_count(session_id, chair, 1)

    (row,) = db.list_session_counts_at_location(session_id)

    assert (row["here"], row["total"]) == (1, 3)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_existing_sessions_get_counts_and_history(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    db.initialize_database()
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        DROP TABLE inventory_session_counts;
        DROP TABLE inventory_session_locations;
        INSERT INTO locations (id, name) VALUES ('loc', 'Warehouse');
        INSERT INTO fixed_asset_categories (id, name) VALUES ('c1', 'IT');
        INSERT INTO fixed_assets (id, category_id, name, category, quantity, initial_value, responsible_person, registration_date)
        VALUES ('a1', 'c1', 'Laptop', 'IT', 4, 10, 'Jane', '2026-01-01'),
               ('a2', 'c1', 'Mouse', 'IT', 1, 10, 'Jane', '2026-01-01');
        INSERT INTO inventory_sessions (id, date_from, date_to, status, responsible_person, location_id, created_at, started_at)
        VALUES ('s1', '2026-01-01', '2026-01-31', 'Completed', 'Jane', 'loc', '2026-01-01', '2026-01-02'),
               ('s2', '2026-02-01', '2026-02-28', 'Active', 'Jane', NULL, '2026-02-01', '2026-02-01');
        INSERT INTO inventory_session_fixed_assets (inventory_session_id, fixed_asset_id, quantity, expected_quantity)
        VALUES ('s1', 'a1', 3, 4), ('s1', 'a2', 0, 1), ('s2', 'a1', 2, 4);
        """
    )
    connection.close()

    db.initialize_database()

    assert _counts("s1") == {("a1", "Warehouse"): 3}  # a count of 0 needs no row
    assert _counts("s2") == {("a1", None): 2}
    assert [(row["location"], row["activated_at"]) for row in db.list_session_location_history("s1")] == [
        ("Warehouse", "2026-01-02")]
    assert db.list_session_location_history("s2") == []
    assert _total("s1", "a1") == (4, 3)
    db.initialize_database()  # running again changes nothing
    assert _counts("s1") == {("a1", "Warehouse"): 3}
