"""Asset locations: the locations list, assets at a location, filters and sessions.

These tests run against a throwaway SQLite file so they exercise the real SQL.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.services.fixed_assets_service import build_filters


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()


@pytest.fixture
def category_id() -> str:
    return str(db.create_fixed_asset_category("IT")["id"])


def _asset(category_id: str, name: str, location_id: str | None = None) -> str:
    asset = db.create_fixed_asset(
        name=name,
        category_id=category_id,
        quantity=1,
        initial_value=10.0,
        responsible_person="Jane",
        registration_date="2026-01-01",
        location_id=location_id,
    )
    return str(asset["id"])


def _names(filters: dict) -> list[str]:
    return sorted(row["name"] for row in db.list_fixed_assets(filters=filters))


def _session(location_id: str | None = None) -> str:
    return str(
        db.create_inventory_session(
            date_from="2026-01-01",
            date_to="2026-01-31",
            responsible_person="Jane",
            location_id=location_id,
        )["id"]
    )


def _save_session(session_id: str, **kwargs) -> None:
    db.update_inventory_session(
        session_id=session_id,
        date_from="2026-01-01",
        date_to="2026-01-31",
        status="New",
        responsible_person="Jane",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Locations list
# ---------------------------------------------------------------------------


def test_location_names_are_unique_ignoring_case():
    db.create_location("Warehouse A")
    with pytest.raises(ValueError):
        db.create_location("warehouse a")


def test_rename_to_a_used_name_is_rejected():
    db.create_location("Warehouse A")
    office = db.create_location("Office")
    with pytest.raises(ValueError):
        db.update_location(office["id"], "WAREHOUSE A")
    assert db.update_location(office["id"], "Head office")["name"] == "Head office"


def test_location_in_use_cannot_be_deleted(category_id):
    location = db.create_location("Warehouse A")
    asset_id = _asset(category_id, "Laptop", location["id"])

    assert db.delete_location(location["id"]) is False

    db.delete_fixed_asset(asset_id)
    assert db.delete_location(location["id"]) is True
    assert db.list_locations() == []
    assert db.create_location("Warehouse A")["id"] != location["id"]


def test_usage_counts_assets_that_are_not_deleted_and_sessions(category_id):
    location = db.create_location("Warehouse A")
    _asset(category_id, "Laptop", location["id"])
    db.delete_fixed_asset(_asset(category_id, "Old laptop", location["id"]))
    _session(location["id"])

    (row,) = db.list_locations_with_usage()
    assert (row["assets_count"], row["sessions_count"]) == (1, 1)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


def test_asset_location_is_saved_and_returned(category_id):
    location = db.create_location("Warehouse A")
    asset_id = _asset(category_id, "Laptop", location["id"])

    asset = db.get_fixed_asset_by_id(asset_id)
    assert (asset["location_id"], asset["location"]) == (location["id"], "Warehouse A")

    db.update_fixed_asset(
        fixed_asset_id=asset_id,
        name="Laptop",
        category_id=category_id,
        quantity=1,
        initial_value=10.0,
        responsible_person="Jane",
        registration_date="2026-01-01",
        location_id=None,
    )
    assert db.get_fixed_asset_by_id(asset_id)["location"] is None


def test_asset_cannot_use_a_missing_or_deleted_location(category_id):
    with pytest.raises(ValueError, match="Location"):
        _asset(category_id, "Laptop", "no-such-location")

    location = db.create_location("Warehouse A")
    db.delete_location(location["id"])
    with pytest.raises(ValueError, match="Location"):
        _asset(category_id, "Laptop", location["id"])


def test_filter_by_location_name_and_no_location(category_id):
    warehouse = db.create_location("Warehouse A")
    office = db.create_location("Office")
    _asset(category_id, "Laptop", warehouse["id"])
    _asset(category_id, "Desk", office["id"])
    _asset(category_id, "Printer")

    assert _names(build_filters(location=["warehouse a"])) == ["Laptop"]
    assert _names(build_filters(location=["Warehouse A", "Office"])) == ["Desk", "Laptop"]
    assert _names(build_filters(location=[db.NO_LOCATION_FILTER])) == ["Printer"]
    assert _names(build_filters(location=f"Office,{db.NO_LOCATION_FILTER}")) == ["Desk", "Printer"]
    assert db.count_fixed_assets(build_filters(location=["Office"])) == 1
    assert _names({"location_id": warehouse["id"]}) == ["Laptop"]


def test_build_filters_location_values():
    filters = build_filters(location=["Office", " ", "Warehouse A"])
    assert filters["location_values"] == ["Office", "Warehouse A"]
    assert filters["location"] == "Office,Warehouse A"
    assert build_filters()["location"] == ""


# ---------------------------------------------------------------------------
# Inventory sessions
# ---------------------------------------------------------------------------


def test_session_location_is_kept_unless_changed():
    warehouse = db.create_location("Warehouse A")
    office = db.create_location("Office")
    session_id = _session(warehouse["id"])

    _save_session(session_id)
    assert db.get_inventory_session_by_id(session_id)["location"] == "Warehouse A"

    _save_session(session_id, location_id=office["id"])
    assert db.get_inventory_session_by_id(session_id)["location"] == "Office"

    _save_session(session_id, location_id=None)
    assert db.get_inventory_session_by_id(session_id)["location_id"] is None


def test_session_keeps_a_location_deleted_later():
    location = db.create_location("Warehouse A")
    session_id = _session(location["id"])
    db.delete_location(location["id"])

    _save_session(session_id, location_id=location["id"])

    assert db.get_inventory_session_by_id(session_id)["location"] == "Warehouse A"
    with pytest.raises(ValueError):
        _session(location["id"])


def test_sessions_filter_by_location():
    warehouse = db.create_location("Warehouse A")
    in_warehouse = _session(warehouse["id"])
    _session()

    rows = db.list_inventory_sessions(location_id=warehouse["id"])
    assert [(row["id"], row["location"]) for row in rows] == [(in_warehouse, "Warehouse A")]
    assert len(db.list_inventory_sessions()) == 2


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_adds_location_columns_to_an_existing_database(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE fixed_asset_categories (id TEXT PRIMARY KEY, name TEXT NOT NULL, deleted_at TEXT);
        CREATE TABLE fixed_assets (
            id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            initial_value REAL NOT NULL,
            responsible_person TEXT NOT NULL,
            registration_date TEXT NOT NULL,
            image_path TEXT,
            deleted_at TEXT
        );
        CREATE TABLE inventory_sessions (
            id TEXT PRIMARY KEY,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            status TEXT NOT NULL,
            responsible_person TEXT NOT NULL
        );
        INSERT INTO fixed_asset_categories (id, name) VALUES ('c1', 'IT');
        INSERT INTO fixed_assets VALUES ('a1', 'c1', 'Laptop', 'IT', 1, 10, 'Jane', '2026-01-01', NULL, NULL);
        INSERT INTO inventory_sessions VALUES ('s1', '2026-01-01', '2026-01-31', 'New', 'Jane');
        """
    )
    connection.close()

    db.initialize_database()

    assert db.get_fixed_asset_by_id("a1")["location_id"] is None
    assert db.get_inventory_session_by_id("s1")["location_id"] is None
    location = db.create_location("Warehouse A")
    _save_session("s1", location_id=location["id"])
    assert db.get_inventory_session_by_id("s1")["location"] == "Warehouse A"
