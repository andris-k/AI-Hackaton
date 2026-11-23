"""Importing fixed assets from CSV: reading and checking files, and saving them."""

from __future__ import annotations

import pytest

from app import db
from app.services import asset_import_service as svc
from app.services.asset_import_service import ImportFileError, parse_assets_csv, parse_number

HEADER = "name,category,location,quantity,initial_value,responsible_person,registration_date\n"


def _parse(text: str | bytes, categories=(), locations=(), names=()):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return parse_assets_csv(
        data, existing_categories=categories, existing_locations=locations, existing_asset_names=names
    )


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------


def test_template_is_valid():
    preview = _parse(svc.template_csv())
    assert preview.can_import
    assert [row.name for row in preview.rows] == ["Dell Latitude 7440", "Office chair"]
    assert preview.rows[1].responsible_person == "Jānis Bērziņš"


def test_excel_style_semicolon_file():
    data = (
        "﻿Name;Category;Location;Quantity;Initial value;Responsible person;Registration date\r\n"
        "Krēsls;Mēbeles;Noliktava;3;1 234,56;Anna Ozola;31.01.2026\r\n"
    ).encode("utf-8")
    preview = _parse(data)

    assert preview.can_import
    (row,) = preview.rows
    assert (row.name, row.category, row.location) == ("Krēsls", "Mēbeles", "Noliktava")
    assert (row.quantity, row.initial_value, row.registration_date) == (3, 1234.56, "2026-01-31")


def test_tab_separated_file_without_optional_columns():
    preview = _parse("name\tcategory\tinitial_value\tresponsible_person\tregistration_date\n"
                     "Desk\tFurniture\t100\tJane\t2026-02-01\n")
    (row,) = preview.rows
    assert (row.quantity, row.location) == (1, "")


def test_missing_required_column():
    with pytest.raises(ImportFileError, match="initial_value"):
        _parse("name,category,responsible_person,registration_date\nDesk,Furniture,Jane,2026-01-01\n")


def test_file_not_in_utf8():
    data = (HEADER + "Krēsls,Mēbeles,,1,10,Anna,2026-01-01\n").encode("cp1257")
    with pytest.raises(ImportFileError, match="UTF-8"):
        _parse(data)


def test_empty_file():
    with pytest.raises(ImportFileError, match="empty"):
        _parse("")


def test_too_many_rows(monkeypatch):
    monkeypatch.setattr(svc, "MAX_ROWS", 2)
    with pytest.raises(ImportFileError, match="more than 2"):
        _parse(HEADER + "A,IT,,1,1,Jane,2026-01-01\n" * 3)


def test_blank_lines_are_skipped_and_line_numbers_kept():
    preview = _parse(HEADER + "\nA,IT,,1,1,Jane,2026-01-01\n,,,,,,\nB,IT,,1,1,Jane,bad\n")
    assert [row.line for row in preview.rows] == [3, 5]
    assert preview.rows[1].errors


def test_unknown_columns_are_ignored():
    preview = _parse("name,category,initial_value,responsible_person,registration_date,Serial no\n"
                     "Desk,Furniture,1,Jane,2026-01-01,XY-1\n")
    assert preview.ignored_columns == ["Serial no"]
    assert preview.can_import


# ---------------------------------------------------------------------------
# Checking rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        (",IT,,1,1,Jane,2026-01-01", "Name is required."),
        ("A,,,1,1,Jane,2026-01-01", "Category is required."),
        (f"{'x' * 101},IT,,1,1,Jane,2026-01-01", "Name must be 100 characters or less."),
        ("A,IT,,1.5,1,Jane,2026-01-01", "Quantity must be a whole number"),
        ("A,IT,,-1,1,Jane,2026-01-01", "Quantity must be a whole number"),
        ("A,IT,,1,,Jane,2026-01-01", "Initial value is required."),
        ("A,IT,,1,abc,Jane,2026-01-01", "Initial value must be a number"),
        ("A,IT,,1,-5,Jane,2026-01-01", "Initial value cannot be negative."),
        ("A,IT,,1,1,,2026-01-01", "Responsible person is required."),
        ("A,IT,,1,1,Jane,01/31/2026", "Registration date must be"),
        ("A,IT,,1,1,Jane,2026-02-30", "Registration date must be"),
    ],
)
def test_row_errors(line, expected):
    preview = _parse(HEADER + line + "\n")
    (row,) = preview.rows
    assert any(error.startswith(expected) for error in row.errors), row.errors
    assert not preview.can_import


def test_new_categories_and_locations_ignore_case():
    preview = _parse(
        HEADER
        + "A,it,office,1,1,Jane,2026-01-01\n"
        + "B,Furniture,Warehouse,1,1,Jane,2026-01-01\n"
        + "C,furniture,warehouse,1,1,Jane,2026-01-01\n",
        categories=["IT"],
        locations=["Office"],
    )
    assert preview.new_categories == ["Furniture"]
    assert preview.new_locations == ["Warehouse"]


def test_duplicate_warnings_do_not_block_the_import():
    preview = _parse(
        HEADER + "Laptop,IT,,1,1,Jane,2026-01-01\nDesk,IT,,1,1,Jane,2026-01-01\ndesk,it,,1,1,Jane,2026-01-01\n",
        names=["LAPTOP"],
    )
    assert "already registered" in preview.rows[0].warnings[0]
    assert preview.rows[2].warnings == ["Same name and category as line 3."]
    assert preview.can_import


@pytest.mark.parametrize(
    "text, expected",
    [("1234.56", 1234.56), ("1234,56", 1234.56), ("1 234,56", 1234.56), ("1,234.56", 1234.56),
     ("1.234,56", 1234.56), ("1 234", 1234.0), ("0", 0.0)],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()


def _row(name: str, category: str = "IT", location: str = "", **overrides) -> dict:
    return {
        "name": name, "category": category, "location": location, "quantity": 2,
        "initial_value": 10.5, "responsible_person": "Jane", "registration_date": "2026-01-01", **overrides,
    }


def test_import_creates_missing_categories_and_locations_once(temp_database):
    db.create_fixed_asset_category("IT")
    db.create_location("Office")

    result = db.import_fixed_assets([
        _row("Laptop", "it", "office"),
        _row("Desk", "Furniture", "Warehouse"),
        _row("Chair", "furniture", "warehouse"),
    ])

    assert (result["created_categories"], result["created_locations"]) == (["Furniture"], ["Warehouse"])
    assets = {row["name"]: row for row in db.list_fixed_assets()}
    assert (assets["Laptop"]["category"], assets["Laptop"]["location"]) == ("IT", "Office")
    assert (assets["Chair"]["category"], assets["Chair"]["location"]) == ("Furniture", "Warehouse")
    assert (assets["Desk"]["quantity"], assets["Desk"]["initial_value"]) == (2, 10.5)
    assert len(db.list_fixed_asset_categories()) == 2


def test_import_is_all_or_nothing(temp_database):
    with pytest.raises(Exception):
        db.import_fixed_assets([_row("Laptop", "New category"), _row("x" * 101)])

    assert db.list_fixed_assets() == []
    assert db.list_fixed_asset_categories() == []


def test_audit_many_stores_one_event_per_asset(temp_database):
    from app.logging_config import audit_many
    from app.repositories import audit_repository

    audit_repository.initialize_audit_storage()
    audit_many("asset.created", [{"asset_id": "a1", "name": "Laptop"}, {"asset_id": "a2", "name": "Desk"}])

    for asset_id, name in (("a1", "Laptop"), ("a2", "Desk")):
        (event,) = audit_repository.list_entity_events("asset", asset_id)
        assert event["event"] == "asset.created" and name in event["details"]
