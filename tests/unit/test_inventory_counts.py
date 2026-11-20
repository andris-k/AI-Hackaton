"""Expected and counted quantities in inventory sessions.

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


def _asset(name: str = "Laptop", quantity: int = 5) -> str:
    category = db.create_fixed_asset_category("IT")
    asset = db.create_fixed_asset(
        name=name,
        category_id=category["id"],
        quantity=quantity,
        initial_value=100.0,
        responsible_person="Jane",
        registration_date="2026-01-01",
    )
    return str(asset["id"])


def _set_asset_quantity(asset_id: str, quantity: int) -> None:
    asset = db.get_fixed_asset_by_id(asset_id)
    db.update_fixed_asset(
        fixed_asset_id=asset_id,
        name=asset["name"],
        category_id=asset["category_id"],
        quantity=quantity,
        initial_value=asset["initial_value"],
        responsible_person=asset["responsible_person"],
        registration_date=asset["registration_date"],
    )


def _session(linked_assets: list[tuple[str, int]] = ()) -> str:
    session = db.create_inventory_session(
        date_from="2026-01-01",
        date_to="2026-01-31",
        responsible_person="Jane",
        linked_assets=linked_assets,
    )
    return str(session["id"])


def _save(session_id: str, status: str, linked_assets: list[tuple[str, int]]) -> None:
    db.update_inventory_session(
        session_id=session_id,
        date_from="2026-01-01",
        date_to="2026-01-31",
        status=status,
        responsible_person="Jane",
        linked_assets=linked_assets,
    )


def _counts(session_id: str) -> dict[str, tuple[int, int]]:
    """Asset name -> (expected, counted)."""
    return {
        row["name"]: (row["expected_quantity"], row["quantity"])
        for row in db.list_fixed_assets_for_inventory_session(session_id)
    }


def test_counted_quantity_of_zero_is_kept():
    asset_id = _asset()
    session_id = _session()
    _save(session_id, "Active", [(asset_id, 0)])

    assert _counts(session_id) == {"Laptop": (5, 0)}


def test_new_session_shows_current_asset_quantity():
    asset_id = _asset(quantity=5)
    session_id = _session()
    _save(session_id, "New", [(asset_id, 3)])

    _set_asset_quantity(asset_id, 7)

    assert _counts(session_id) == {"Laptop": (7, 3)}


def test_expected_quantity_is_saved_when_session_starts():
    asset_id = _asset(quantity=5)
    session_id = _session()
    _save(session_id, "New", [(asset_id, 4)])
    _save(session_id, "Active", [(asset_id, 4)])

    _set_asset_quantity(asset_id, 9)
    _save(session_id, "Active", [(asset_id, 3)])
    _save(session_id, "Completed", [(asset_id, 3)])

    assert _counts(session_id) == {"Laptop": (5, 3)}


def test_asset_added_while_active_gets_quantity_at_that_time():
    first_id = _asset("Laptop", quantity=5)
    second_id = _asset("Monitor", quantity=2)
    session_id = _session()
    _save(session_id, "Active", [(first_id, 5)])

    _set_asset_quantity(second_id, 3)
    _save(session_id, "Active", [(first_id, 5), (second_id, 1)])
    _set_asset_quantity(second_id, 8)

    assert _counts(session_id) == {"Laptop": (5, 5), "Monitor": (3, 1)}


def test_reopening_keeps_expected_quantities():
    asset_id = _asset(quantity=5)
    session_id = _session()
    _save(session_id, "Active", [(asset_id, 5)])
    _save(session_id, "Completed", [(asset_id, 5)])

    _set_asset_quantity(asset_id, 1)
    _save(session_id, "Active", [(asset_id, 5)])

    assert _counts(session_id) == {"Laptop": (5, 5)}


def test_removed_and_added_again_gets_current_quantity():
    asset_id = _asset(quantity=5)
    session_id = _session()
    _save(session_id, "Active", [(asset_id, 5)])
    _save(session_id, "Active", [])

    _set_asset_quantity(asset_id, 6)
    _save(session_id, "Active", [(asset_id, 6)])

    assert _counts(session_id) == {"Laptop": (6, 6)}


def test_negative_counted_quantity_is_dropped():
    asset_id = _asset()
    session_id = _session()
    _save(session_id, "Active", [(asset_id, -1)])

    assert _counts(session_id) == {}


def test_migrates_links_that_required_positive_quantity(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    db.initialize_database()
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        DROP TABLE inventory_session_fixed_assets;
        CREATE TABLE inventory_session_fixed_assets (
            inventory_session_id TEXT NOT NULL,
            fixed_asset_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            PRIMARY KEY (inventory_session_id, fixed_asset_id),
            FOREIGN KEY (inventory_session_id) REFERENCES inventory_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (fixed_asset_id) REFERENCES fixed_assets(id) ON DELETE CASCADE
        );
        INSERT INTO fixed_asset_categories (id, name) VALUES ('c1', 'IT');
        INSERT INTO fixed_assets (id, category_id, name, category, quantity, initial_value,
                                  responsible_person, registration_date)
        VALUES ('a1', 'c1', 'Laptop', 'IT', 5, 10, 'Jane', '2026-01-01');
        INSERT INTO inventory_sessions (id, date_from, date_to, status, responsible_person)
        VALUES ('s-new', '2026-01-01', '2026-01-31', 'New', 'Jane'),
               ('s-done', '2026-01-01', '2026-01-31', 'Completed', 'Jane');
        INSERT INTO inventory_session_fixed_assets VALUES ('s-new', 'a1', 2), ('s-done', 'a1', 4);
        """
    )
    connection.close()

    db.initialize_database()

    _set_asset_quantity("a1", 9)
    assert _counts("s-new") == {"Laptop": (9, 2)}
    assert _counts("s-done") == {"Laptop": (5, 4)}

    _save("s-new", "Active", [("a1", 0)])
    assert _counts("s-new") == {"Laptop": (9, 0)}
