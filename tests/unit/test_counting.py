"""Counting by scanning labels, and the printable QR labels.

Database tests run against a throwaway SQLite file so they exercise the real SQL.
"""

from __future__ import annotations

import re

import pytest
import segno

from app import db
from app.services import asset_labels_service as labels
from app.services.inventory_sessions_service import count_message, is_stale, parse_asset_code


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()


@pytest.fixture
def category_id() -> str:
    return str(db.create_fixed_asset_category("IT")["id"])


def _asset(category_id: str, name: str = "Laptop", quantity: int = 3, location_id: str | None = None) -> str:
    return str(
        db.create_fixed_asset(
            name=name,
            category_id=category_id,
            quantity=quantity,
            initial_value=10.0,
            responsible_person="Jane",
            registration_date="2026-01-01",
            location_id=location_id,
        )["id"]
    )


def _session(status: str = "Active", linked: list[tuple[str, int]] = (), location_id: str | None = None) -> str:
    session_id = str(
        db.create_inventory_session(
            date_from="2026-01-01", date_to="2026-01-31", responsible_person="Jane", location_id=location_id
        )["id"]
    )
    db.update_inventory_session(
        session_id=session_id,
        date_from="2026-01-01",
        date_to="2026-01-31",
        status=status,
        responsible_person="Jane",
        linked_assets=linked,
    )
    return session_id


def _count(session_id: str, asset_id: str) -> int:
    (row,) = [row for row in db.list_fixed_assets_for_inventory_session(session_id) if row["id"] == asset_id]
    return int(row["quantity"])


# ---------------------------------------------------------------------------
# adjust_inventory_count
# ---------------------------------------------------------------------------


def test_scan_adds_one_to_a_linked_asset(category_id):
    asset_id = _asset(category_id)
    session_id = _session(linked=[(asset_id, 0)])

    outcome = db.adjust_inventory_count(session_id, asset_id, 1)
    db.adjust_inventory_count(session_id, asset_id, 1)

    assert outcome["result"] == "counted"
    assert (outcome["quantity"], outcome["expected_quantity"]) == (1, 3)
    assert _count(session_id, asset_id) == 2


def test_count_never_goes_below_zero(category_id):
    asset_id = _asset(category_id)
    session_id = _session(linked=[(asset_id, 1)])

    db.adjust_inventory_count(session_id, asset_id, -1)
    outcome = db.adjust_inventory_count(session_id, asset_id, -1)

    assert outcome["quantity"] == 0


def test_scanning_an_asset_not_in_the_session_adds_it(category_id):
    asset_id = _asset(category_id, quantity=4)
    session_id = _session()

    outcome = db.adjust_inventory_count(session_id, asset_id, 1)

    assert outcome["result"] == "added"
    assert outcome["other_location"] is False
    (row,) = db.list_fixed_assets_for_inventory_session(session_id)
    assert (row["quantity"], row["expected_quantity"]) == (1, 4)


def test_asset_from_another_location_is_added_and_flagged(category_id):
    warehouse = db.create_location("Warehouse")
    office = db.create_location("Office")
    asset_id = _asset(category_id, location_id=office["id"])
    session_id = _session(location_id=warehouse["id"])

    outcome = db.adjust_inventory_count(session_id, asset_id, 1)

    assert (outcome["result"], outcome["other_location"]) == ("added", True)


@pytest.mark.parametrize("status", ["New", "Completed", "Cancelled"])
def test_only_active_sessions_can_be_counted(category_id, status):
    asset_id = _asset(category_id)
    session_id = _session(status=status, linked=[(asset_id, 1)])

    assert db.adjust_inventory_count(session_id, asset_id, 1)["result"] == "not_active"
    assert _count(session_id, asset_id) == 1


def test_deleted_asset_is_not_added_but_a_linked_one_can_be_counted(category_id):
    linked_id = _asset(category_id, "Linked")
    other_id = _asset(category_id, "Other")
    session_id = _session(linked=[(linked_id, 0)])
    db.delete_fixed_asset(linked_id)
    db.delete_fixed_asset(other_id)

    assert db.adjust_inventory_count(session_id, other_id, 1)["result"] == "asset_deleted"
    assert db.adjust_inventory_count(session_id, linked_id, 1)["result"] == "counted"


def test_minus_on_an_asset_not_in_the_session_does_nothing(category_id):
    asset_id = _asset(category_id)
    session_id = _session()

    assert db.adjust_inventory_count(session_id, asset_id, -1)["result"] == "not_linked"
    assert db.list_fixed_assets_for_inventory_session(session_id) == []


def test_unknown_session_or_asset(category_id):
    session_id = _session()
    assert db.adjust_inventory_count("missing", _asset(category_id), 1)["result"] == "session_not_found"
    assert db.adjust_inventory_count(session_id, "missing", 1)["result"] == "asset_not_found"


def test_counting_marks_the_session_as_changed(category_id):
    asset_id = _asset(category_id)
    session_id = _session(linked=[(asset_id, 0)])
    loaded = str(db.get_inventory_session_by_id(session_id)["updated_at"])

    db.adjust_inventory_count(session_id, asset_id, 1)

    assert is_stale(loaded, db.get_inventory_session_by_id(session_id)["updated_at"])


def test_is_stale_ignores_forms_without_the_field():
    assert is_stale("", "2026-01-01T00:00:00+00:00") is False
    assert is_stale("a", "a") is False


# ---------------------------------------------------------------------------
# Finding assets and sessions
# ---------------------------------------------------------------------------


def test_find_by_short_id(category_id):
    asset_id = _asset(category_id)
    db.delete_fixed_asset(_asset(category_id, "Deleted"))

    assert db.find_fixed_asset_ids_by_prefix(asset_id[:8].upper()) == [asset_id]
    assert db.find_fixed_asset_ids_by_prefix("zzzzzzzz") == []


def test_active_sessions_for_an_asset(category_id):
    warehouse = db.create_location("Warehouse")
    office = db.create_location("Office")
    asset_id = _asset(category_id, location_id=warehouse["id"])
    all_locations = _session()
    same_location = _session(location_id=warehouse["id"])
    other_but_linked = _session(location_id=office["id"], linked=[(asset_id, 2)])
    _session(location_id=office["id"])
    _session(status="New")

    rows = {row["id"]: row["quantity"] for row in db.list_active_sessions_for_asset(asset_id)}

    assert rows == {all_locations: None, same_location: None, other_but_linked: 2}


# ---------------------------------------------------------------------------
# Codes and messages
# ---------------------------------------------------------------------------


ASSET_ID = "3f2a9c1b-0d4e-4f6a-8b7c-1234567890ab"


@pytest.mark.parametrize(
    "code, expected",
    [
        (f"https://assets.example.com/fixed-assets/id/{ASSET_ID}", (ASSET_ID, None)),
        (f"  {ASSET_ID.upper()}  ", (ASSET_ID, None)),
        ("3F2A9C1B", (None, "3f2a9c1b")),
        ("3f2a9c", (None, "3f2a9c")),
        ("3f2a", (None, None)),
        ("hello world", (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_asset_code(code, expected):
    assert parse_asset_code(code) == expected


def test_count_messages():
    text, kind = count_message({"result": "counted", "name": "Laptop", "quantity": 2, "expected_quantity": 3})
    assert (text, kind) == ("Laptop: counted 2 of 3.", "success")
    text, kind = count_message({"result": "added", "name": "Desk", "quantity": 1, "other_location": True})
    assert "another location" in text and kind == "info"
    assert count_message({"result": "asset_not_found"})[1] == "error"


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class _RecordingPDF:
    def __init__(self) -> None:
        self.rects: list[tuple[float, float, float, float]] = []

    def set_fill_color(self, *args) -> None:
        pass

    def rect(self, x, y, w, h, style=None) -> None:
        self.rects.append((x, y, w, h))


def test_qr_squares_match_the_code():
    data = labels.asset_url("https://assets.example.com", ASSET_ID)
    pdf = _RecordingPDF()
    labels._draw_qr(pdf, data, 0, 0, 30)

    matrix = [list(row) for row in segno.make(data, error="m", mask=labels.QR_MASK).matrix]
    module = 30 / (len(matrix) + 4)
    drawn = [[0] * len(matrix) for _ in matrix]
    for x, y, w, h in pdf.rects:
        row = round(y / module) - 2
        first = round(x / module) - 2
        for col in range(first, first + round(w / module)):
            drawn[row][col] = 1
    assert drawn == matrix


def test_labels_pdf_has_one_page_per_21_labels():
    assets = [
        {"id": f"{i:08x}-0000-4000-8000-000000000000", "name": f"Asset {i}", "category": "IT", "location": None}
        for i in range(22)
    ]
    pdf = labels.build_labels_pdf(assets, "https://assets.example.com")

    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2


def test_labels_pdf_without_assets():
    assert labels.build_labels_pdf([], "http://localhost").startswith(b"%PDF")
