from datetime import date

from app.services import fixed_assets_report_service as svc


def _asset(name: str, category: str, quantity: int, value: float) -> dict:
    return {
        "name": name,
        "category": category,
        "quantity": quantity,
        "initial_value": value,
        "responsible_person": "Anna",
        "registration_date": "2026-01-01",
    }


def test_report_filename_uses_date() -> None:
    assert svc.report_filename(date(2026, 11, 15)) == "fixed-assets-2026-11-15.pdf"


def test_rows_sorted_by_category_then_name_with_line_totals() -> None:
    rows = svc._rows([
        _asset("Desk", "Furniture", 2, 100.0),
        _asset("laptop", "IT", 3, 50.0),
        _asset("Chair", "furniture", 1, 10.0),
    ])
    assert [r["name"] for r in rows] == ["Chair", "Desk", "laptop"]
    assert rows[1]["total"] == 200.0


def test_category_summary_aggregates() -> None:
    rows = svc._rows([_asset("A", "IT", 2, 10.0), _asset("B", "IT", 1, 5.0), _asset("C", "Furniture", 4, 1.0)])
    summary = {c["category"]: c for c in svc._category_summary(rows)}
    assert summary["IT"] == {"category": "IT", "assets": 2, "quantity": 3, "total": 25.0}
    assert summary["Furniture"]["total"] == 4.0


def test_build_report_returns_pdf_bytes() -> None:
    assert svc.build_fixed_assets_report([_asset("A", "IT", 1, 1.0)]).startswith(b"%PDF")
    assert svc.build_fixed_assets_report([]).startswith(b"%PDF")
