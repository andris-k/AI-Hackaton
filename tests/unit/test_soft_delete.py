"""Logical (soft) deletion of fixed assets and categories.

These tests run against a throwaway SQLite file so they exercise the real SQL.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import db


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()


def _asset(category_id: str, name: str = "Laptop", quantity: int = 2) -> sqlite3.Row:
    return db.create_fixed_asset(
        name=name,
        category_id=category_id,
        quantity=quantity,
        initial_value=100.0,
        responsible_person="Jane",
        registration_date="2026-01-01",
    )


def test_deleted_asset_is_hidden_from_lists_but_still_readable():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])

    assert db.delete_fixed_asset(asset["id"]) is True

    assert db.list_fixed_assets() == []
    assert db.count_fixed_assets() == 0
    assert db.count_fixed_assets({"name": "Laptop"}) == 0
    row = db.get_fixed_asset_by_id(asset["id"])
    assert row is not None
    assert row["deleted_at"] is not None


def test_deleting_twice_reports_not_found():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])

    assert db.delete_fixed_asset(asset["id"]) is True
    assert db.delete_fixed_asset(asset["id"]) is False


def test_deleted_asset_cannot_be_updated():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])
    db.delete_fixed_asset(asset["id"])

    db.update_fixed_asset(
        fixed_asset_id=asset["id"],
        name="Renamed",
        category_id=category["id"],
        quantity=5,
        initial_value=1.0,
        responsible_person="Jane",
        registration_date="2026-01-01",
    )

    assert db.get_fixed_asset_by_id(asset["id"])["name"] == "Laptop"


def test_completed_session_keeps_deleted_asset():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])
    session = db.create_inventory_session(
        date_from="2026-01-01",
        date_to="2026-01-31",
        responsible_person="Jane",
        linked_assets=[(asset["id"], 2)],
    )
    db.delete_fixed_asset(asset["id"])

    # Status changes re-save the links; the deleted asset must survive that.
    for status in ("Active", "Completed"):
        db.update_inventory_session(
            session_id=session["id"],
            date_from="2026-01-01",
            date_to="2026-01-31",
            status=status,
            responsible_person="Jane",
            linked_assets=db.list_linked_fixed_assets_for_inventory_session(session["id"]),
        )

    linked = db.list_fixed_assets_for_inventory_session(session["id"])
    assert [row["id"] for row in linked] == [asset["id"]]
    assert linked[0]["deleted_at"] is not None
    assert linked[0]["category"] == "IT"
    assert db.get_inventory_session_by_id(session["id"])["linked_assets_count"] == 1


def test_deleted_asset_cannot_be_newly_linked():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])
    db.delete_fixed_asset(asset["id"])

    session = db.create_inventory_session(
        date_from="2026-01-01",
        date_to="2026-01-31",
        responsible_person="Jane",
        linked_assets=[(asset["id"], 1)],
    )

    assert db.list_fixed_assets_for_inventory_session(session["id"]) == []


def test_category_in_use_by_active_asset_cannot_be_deleted():
    category = db.create_fixed_asset_category("IT")
    _asset(category["id"])

    assert db.delete_fixed_asset_category(category["id"]) is False
    assert db.get_fixed_asset_category_by_id(category["id"]) is not None


def test_category_used_only_by_deleted_assets_can_be_deleted():
    category = db.create_fixed_asset_category("IT")
    asset = _asset(category["id"])
    session = db.create_inventory_session(
        date_from="2026-01-01",
        date_to="2026-01-31",
        responsible_person="Jane",
        linked_assets=[(asset["id"], 1)],
    )
    db.delete_fixed_asset(asset["id"])

    assert db.delete_fixed_asset_category(category["id"]) is True

    assert db.list_fixed_asset_categories() == []
    assert db.list_fixed_asset_categories_with_usage() == []
    assert db.get_fixed_asset_category_by_id(category["id"]) is None
    # History still resolves the category name.
    assert db.list_fixed_assets_for_inventory_session(session["id"])[0]["category"] == "IT"
    assert db.get_fixed_asset_by_id(asset["id"])["category"] == "IT"


def test_assets_cannot_use_a_deleted_category():
    category = db.create_fixed_asset_category("IT")
    db.delete_fixed_asset_category(category["id"])

    with pytest.raises(ValueError):
        _asset(category["id"])


def test_deleted_category_name_can_be_reused():
    old = db.create_fixed_asset_category("IT")
    db.delete_fixed_asset_category(old["id"])

    new = db.create_fixed_asset_category("IT")
    assert new["id"] != old["id"]

    other = db.create_fixed_asset_category("Furniture")
    db.update_fixed_asset_category(other["id"], "Office")
    with pytest.raises(ValueError):
        db.update_fixed_asset_category(other["id"], "it")


def test_usage_count_ignores_deleted_assets():
    category = db.create_fixed_asset_category("IT")
    _asset(category["id"], name="Kept")
    db.delete_fixed_asset(_asset(category["id"], name="Gone")["id"])

    (row,) = db.list_fixed_asset_categories_with_usage()
    assert row["assets_count"] == 1


def test_migrates_legacy_unique_category_table(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE fixed_asset_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE CHECK (length(name) <= 100)
        );
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
            FOREIGN KEY (category_id) REFERENCES fixed_asset_categories(id)
        );
        INSERT INTO fixed_asset_categories (id, name) VALUES ('c1', 'IT');
        INSERT INTO fixed_assets VALUES ('a1', 'c1', 'Laptop', 'IT', 1, 10, 'Jane', '2026-01-01', NULL);
        """
    )
    connection.close()

    db.initialize_database()

    assert [row["name"] for row in db.list_fixed_asset_categories()] == ["IT"]
    assert db.get_fixed_asset_by_id("a1")["deleted_at"] is None
    db.delete_fixed_asset("a1")
    db.delete_fixed_asset_category("c1")
    assert db.create_fixed_asset_category("IT")["id"] != "c1"
