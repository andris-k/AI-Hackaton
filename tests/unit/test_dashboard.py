"""Dashboard and analytics: the figures and how they are presented."""

from __future__ import annotations

from datetime import date

import pytest

from app import db
from app.repositories import audit_repository
from app.repositories import reporting_repository as reports
from app.services import dashboard_service as svc


@pytest.fixture
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    db.initialize_database()
    audit_repository.initialize_audit_storage()


def _asset(category: str, name: str, quantity: int, value: float, *, location_id=None, registered="2026-03-10") -> str:
    category_id = db.create_fixed_asset_category(category)["id"]  # returns the existing one if the name is taken
    return str(db.create_fixed_asset(
        name=name, category_id=category_id, quantity=quantity, initial_value=value,
        responsible_person="Jane", registration_date=registered, location_id=location_id,
    )["id"])


def _session(status: str, linked: list[tuple[str, int]], location_id=None) -> str:
    session_id = str(db.create_inventory_session(
        date_from="2026-11-01", date_to="2026-11-30", responsible_person="Jane", location_id=location_id,
    )["id"])
    for step in (["Active"] if status == "Active" else ["Active", status]):
        db.update_inventory_session(
            session_id=session_id, date_from="2026-11-01", date_to="2026-11-30", status=step,
            responsible_person="Jane", linked_assets=linked,
        )
    return session_id


# ---------------------------------------------------------------------------
# Figures from the database
# ---------------------------------------------------------------------------


def test_asset_summary(temp_database):
    warehouse = db.create_location("Warehouse")
    _asset("IT", "Laptop", 2, 1000.0, location_id=warehouse["id"])
    _asset("Furniture", "Chair", 10, 50.5)
    db.delete_fixed_asset(_asset("IT", "Old", 1, 999.0))
    _session("New", [])

    summary = reports.asset_summary()

    assert (summary["assets"], summary["total_value"], summary["without_location"]) == (2, 2505.0, 1)
    assert (summary["categories"], summary["locations"]) == (2, 1)
    assert summary["sessions_by_status"] == {"New": 1}


def test_session_progress_compares_with_expected_quantity(temp_database):
    laptop = _asset("IT", "Laptop", 3, 10.0)
    chair = _asset("Furniture", "Chair", 5, 10.0)
    session_id = _session("Active", [(laptop, 3), (chair, 4)])
    # Expected quantities were saved at start; a later edit doesn't change the result.
    db.update_fixed_asset(fixed_asset_id=chair, name="Chair", category_id=db.get_fixed_asset_by_id(chair)["category_id"],
                          quantity=4, initial_value=10.0, responsible_person="Jane", registration_date="2026-03-10")

    (row,) = reports.sessions_with_progress("Active")
    progress = svc.session_progress(row)

    assert row["id"] == session_id
    assert (progress["matched"], progress["total"], progress["differences"], progress["percent"]) == (1, 2, 1, 50)
    assert progress["label"] == "1 of 2 assets match the expected quantity"
    assert progress["title"] == "2026-11-01 – 2026-11-30 · All locations"


def test_totals_by_category_and_location(temp_database):
    warehouse = db.create_location("Warehouse")
    _asset("IT", "Laptop", 2, 1000.0, location_id=warehouse["id"])
    _asset("IT", "Mouse", 4, 10.0)
    _asset("Furniture", "Chair", 1, 50.0)

    by_category = [(row["label"], row["assets"], row["value"]) for row in reports.totals_by("category")]
    by_location = [(row["label"], row["assets"]) for row in reports.totals_by("location")]

    assert by_category == [("IT", 2, 2040.0), ("Furniture", 1, 50.0)]
    assert by_location == [("Warehouse", 1), (None, 2)]
    with pytest.raises(ValueError):
        reports.totals_by("colour")


def test_registrations_by_month(temp_database):
    _asset("IT", "A", 1, 1.0, registered="2026-01-05")
    _asset("IT", "B", 1, 1.0, registered="2026-01-20")
    _asset("IT", "C", 1, 1.0, registered="2025-12-31")

    assert reports.registrations_by_month("2026-01") == {"2026-01": 2}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_attention_items_order_and_admin_only_approvals():
    results = [{"id": "s1", "title": "Nov · Garage", "differences": 2}, {"id": "s2", "title": "Oct", "differences": 0}]
    items = svc.attention_items(
        is_admin=True, pending_accounts=1, without_location=3, recent_results=results, new_sessions=2,
    )
    assert [item["kind"] for item in items] == ["Approval", "Results", "Register", "Planning"]
    assert items[0]["text"] == "1 account is waiting for approval"
    assert items[1]["text"] == "Nov · Garage was completed with 2 differences"
    assert items[2]["href"] == "/fixed-assets?location=%28none%29"

    not_admin = svc.attention_items(
        is_admin=False, pending_accounts=1, without_location=0, recent_results=[], new_sessions=0,
    )
    assert not_admin == []


def test_dashboard_for_admin_and_ordinary_user(temp_database):
    admin = db.create_user("boss@example.com", "pw", is_admin=True)
    db.create_user("user@example.com", "pw")
    db.create_user("new@example.com", "pw", status="pending")
    laptop = _asset("IT", "Laptop", 1, 100.0)
    _session("Active", [(laptop, 1)])
    audit_repository.record_event("asset.created", admin["email"], None, {"asset_id": laptop, "name": "Laptop"})
    audit_repository.record_event("auth.login", admin["email"], None, {"user_id": admin["id"]})

    for_admin = svc.build_dashboard("boss@example.com")
    for_user = svc.build_dashboard("user@example.com")

    assert [s["complete"] for s in for_admin["active_sessions"]] == [True]
    assert [t["value"] for t in for_admin["tiles"]] == ["1", "100.00", "1", "1"]
    assert [item["kind"] for item in for_admin["attention"]] == ["Approval", "Register"]
    assert [row["event"] for row in for_admin["activity"]] == ["asset.created"]  # logins left out
    assert [item["kind"] for item in for_user["attention"]] == ["Register"]
    assert for_user["activity"] == []


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _rows(*items):
    return [{"label": label, "value": value, "assets": assets} for label, value, assets in items]


def test_bar_rows_sort_by_measure_and_scale_to_the_largest():
    rows = _rows(("IT", 1000.0, 2), ("Furniture", 500.0, 8), (None, 250.0, 1))

    by_value = svc.bar_rows(rows, "value", empty_label="No location")
    by_count = svc.bar_rows(rows, "count", empty_label="No location")

    assert [(r["label"], r["display"], r["percent"]) for r in by_value] == [
        ("IT", "1 000.00", 100.0), ("Furniture", "500.00", 50.0), ("No location", "250.00", 25.0)]
    assert [(r["label"], r["display"]) for r in by_count] == [("Furniture", "8"), ("IT", "2"), ("No location", "1")]
    assert by_value[0]["detail"] == "2 assets · 1 000.00"


def test_bar_rows_fold_the_long_tail_into_other():
    rows = _rows(*[(f"C{i}", float(100 - i), 1) for i in range(12)])
    bars = svc.bar_rows(rows, "value", max_bars=8)

    assert len(bars) == 8
    assert bars[-1]["label"] == "Other (5)"
    assert bars[-1]["display"] == svc.fmt_money(sum(100 - i for i in range(7, 12)))


def test_month_columns_cover_twelve_months_across_the_year_boundary():
    columns = svc.month_columns({"2026-02": 4, "2025-12": 8}, date(2026, 2, 15))

    assert [c["key"] for c in columns][:2] == ["2025-03", "2025-04"]
    assert columns[-1]["key"] == "2026-02"
    assert [(c["key"], c["count"], c["percent"]) for c in columns if c["count"]] == [
        ("2025-12", 8, 100.0), ("2026-02", 4, 50.0)]
    assert [c["key"] for c in columns if c["is_peak"]] == ["2025-12"]
    assert svc.first_month(date(2026, 2, 15)) == "2025-03"


def test_month_columns_without_data():
    columns = svc.month_columns({}, date(2026, 6, 1))
    assert all(c["count"] == 0 and c["percent"] == 0 and not c["is_peak"] for c in columns)


def test_build_analytics(temp_database):
    laptop = _asset("IT", "Laptop", 2, 300.0, registered=date.today().isoformat())
    _session("Completed", [(laptop, 1)])

    data = svc.build_analytics("count")
    unknown_measure = svc.build_analytics("nonsense")

    assert data["measure_label"] == "Number of assets" and unknown_measure["measure"] == "value"
    assert [t["value"] for t in data["tiles"]] == ["1", "600.00", "600.00", "0%"]
    assert data["months"][-1]["count"] == 1 and data["months_total"] == 1
    assert [(r["display"], r["detail"]) for r in data["session_results"]] == [
        ("0%", "0 of 1 assets match the expected quantity")]
