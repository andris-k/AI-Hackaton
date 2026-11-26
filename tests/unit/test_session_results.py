"""Results of a closed inventory session: statuses, values, per location, timeline, counted by, CSV."""

from __future__ import annotations

import csv
import io

import pytest

from app import db
from app.repositories import audit_repository
from app.services import inventory_report_service as report
from app.services import session_results_service as results


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()
    audit_repository.initialize_audit_storage()


def _asset(name: str, quantity: int, value: float, location_id: str | None) -> str:
    category_id = db.create_fixed_asset_category("Furniture")["id"]
    return str(db.create_fixed_asset(
        name=name, category_id=category_id, quantity=quantity, initial_value=value,
        responsible_person="Jane", registration_date="2026-01-01", location_id=location_id,
    )["id"])


@pytest.fixture
def session() -> dict:
    """Room A and Room B; chairs found partly in B; a desk missing; a lamp never counted;
    a monitor extra; a cabinet matched."""
    user = db.create_user("anna@example.com", "pw")
    room_a = str(db.create_location("Room A")["id"])
    room_b = str(db.create_location("Room B")["id"])
    chair = _asset("Chair", 5, 10.0, room_a)
    desk = _asset("Desk", 1, 300.0, room_a)
    lamp = _asset("Lamp", 2, 20.0, room_b)
    monitor = _asset("Monitor", 1, 100.0, room_b)
    cabinet = _asset("Cabinet", 1, 50.0, room_b)
    session_id = str(db.create_inventory_session(
        date_from="2026-12-01", date_to="2026-12-31", responsible_person="Jane", location_id=room_a,
        created_by_user_id=user["id"],
    )["id"])
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status="Active",
        responsible_person="Jane", linked_assets=[(chair, 3), (desk, 0), (lamp, 0)], actor_user_id=user["id"],
    )
    db.adjust_inventory_count(session_id, desk, None, quantity=0, keep_zero=True)
    db.set_active_location(session_id, room_b, user["id"])
    for asset_id, delta in ((chair, 1), (monitor, 2), (cabinet, 1)):
        db.adjust_inventory_count(session_id, asset_id, delta)
        audit_repository.record_event("inventory_session.count_changed", "anna@example.com", None,
                                      {"session_id": session_id, "asset_id": asset_id, "delta": delta, "location": "Room B"})
    db.update_inventory_session(
        session_id=session_id, date_from="2026-12-01", date_to="2026-12-31", status="Completed",
        responsible_person="Jane", completion_reason="Yearly count", actor_user_id=user["id"],
    )
    return {"id": session_id, "room_a": room_a, "room_b": room_b}


def _session_row(session_id: str):
    return db.get_inventory_session_by_id(session_id)


def test_rows_statuses_differences_and_values(session):
    rows = {r["name"]: r for r in results.result_rows(_session_row(session["id"]))}

    assert {name: r["status_label"] for name, r in rows.items()} == {
        "Chair": "Missing −1", "Desk": "Not found", "Lamp": "Not counted", "Monitor": "Extra +1", "Cabinet": "Matched",
    }
    assert (rows["Desk"]["difference_value"], rows["Desk"]["difference_value_label"]) == (-300.0, "−300.00")
    assert rows["Monitor"]["difference_value_label"] == "+100.00"
    assert rows["Cabinet"]["difference_value_label"] == "—"
    assert rows["Chair"]["counted_at"] == "Counted at Room A: 3 · Room B: 1"
    order = [r["name"] for r in results.result_rows(_session_row(session["id"]))]
    assert order == ["Desk", "Monitor", "Lamp", "Chair", "Cabinet"]  # largest value of difference first


def test_tiles(session):
    tiles = results.tiles(results.result_rows(_session_row(session["id"])))

    assert (tiles["total"], tiles["matched"], tiles["matched_percent"]) == (5, 1, 20)
    assert (tiles["missing"], tiles["missing_items"], tiles["extra"], tiles["extra_items"]) == (1, 1, 1, 1)
    assert (tiles["not_found"], tiles["not_counted"], tiles["differences"]) == (2, 1, 4)
    assert (tiles["missing_value"], tiles["extra_value"]) == ("350.00", "100.00")


def test_per_location(session):
    data = results.build_results(_session_row(session["id"]))
    by_name = {row["name"]: row for row in data["per_location"]}

    assert by_name["Room A"] == {
        "name": "Room A", "registered": 2, "counted": 1, "matched": 0, "missing": 2, "found_away": 0,
        "when": by_name["Room A"]["when"],
    }
    room_b = by_name["Room B"]
    assert (room_b["registered"], room_b["counted"], room_b["matched"], room_b["missing"], room_b["found_away"]) == (3, 3, 1, 1, 1)


def test_timeline_includes_locations_reopen_and_completion(session):
    audit_repository.record_event("inventory_session.reopened", "boss@example.com", None,
                                  {"session_id": session["id"], "reason": "Recount Room B"})
    data = results.build_results(_session_row(session["id"]))

    kinds = [(t["kind"], t["what"]) for t in data["timeline"]]
    # In a test everything happens within one second; the reopen (stored to the
    # second) may land anywhere, so check the order of the session's own steps.
    steps = [k for k in kinds if k[0] != "reopen"]
    assert steps[0] == ("start", "Created") and steps[-1] == ("end", "Completed")
    assert ("location", "Counting at Room A") in kinds and ("location", "Counting at Room B") in kinds
    assert ("active", "Started") in kinds
    completed = next(t for t in data["timeline"] if t["kind"] == "end")
    assert completed["detail"] == "by anna@example.com · “Yearly count”"
    reopened = next(t for t in data["timeline"] if t["kind"] == "reopen")
    assert reopened["detail"] == "by boss@example.com · “Recount Room B”"


def test_counted_by_comes_from_the_audit_log(session):
    (person,) = results.build_results(_session_row(session["id"]))["counted_by"]

    assert (person["name"], person["assets"], person["where"], person["percent"]) == ("anna@example.com", 3, "Room B", 100)


def test_results_csv(session):
    rows = list(csv.reader(io.StringIO(results.results_csv(_session_row(session["id"])))))

    assert rows[0] == list(results.CSV_HEADER)
    desk = next(r for r in rows[1:] if r[1] == "Desk")
    assert desk[3:] == ["Room A", "Not found", "Not found at Room A", "1", "0", "-1", "300.00", "-300.00"]


def test_pdf_with_differences_only(session):
    inv_session = _session_row(session["id"])
    assets = db.list_fixed_assets_for_inventory_session(session["id"])

    full = report.build_session_report(inv_session, assets)
    differences = report.build_session_report(inv_session, assets, only_differences=True)

    assert full.startswith(b"%PDF") and differences.startswith(b"%PDF")
    assert differences != full
