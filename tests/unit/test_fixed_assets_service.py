"""Unit tests for app.services.fixed_assets_service.

All functions under test are pure (no I/O), so no fixtures or mocking needed.
"""

from __future__ import annotations

import pytest

from app.services.fixed_assets_service import (
    build_filters,
    normalize_paging,
    validate_list_filters,
)

# ---------------------------------------------------------------------------
# build_filters
# ---------------------------------------------------------------------------


def test_build_filters_defaults_to_empty_strings():
    f = build_filters()
    assert f["name"] == ""
    assert f["category"] == ""
    assert f["category_values"] == []
    assert f["initial_value_from"] == ""
    assert f["initial_value_to"] == ""
    assert f["responsible_person"] == ""
    assert f["registration_date_from"] == ""
    assert f["registration_date_to"] == ""


def test_build_filters_strips_whitespace():
    f = build_filters(name="  Asset  ", responsible_person=" Jane ")
    assert f["name"] == "Asset"
    assert f["responsible_person"] == "Jane"


def test_build_filters_category_list():
    f = build_filters(category=["Electronics", "Furniture"])
    assert f["category_values"] == ["Electronics", "Furniture"]
    assert "Electronics" in f["category"]
    assert "Furniture" in f["category"]


def test_build_filters_category_string_comma_separated():
    f = build_filters(category="Electronics, Furniture")
    assert f["category_values"] == ["Electronics", "Furniture"]


def test_build_filters_category_list_ignores_blank_entries():
    f = build_filters(category=["Electronics", "", "  "])
    assert f["category_values"] == ["Electronics"]


def test_build_filters_category_empty_list():
    f = build_filters(category=[])
    assert f["category_values"] == []
    assert f["category"] == ""


# ---------------------------------------------------------------------------
# normalize_paging
# ---------------------------------------------------------------------------


def test_normalize_paging_standard_case():
    page, size, total_pages = normalize_paging(page=2, page_size=10, total_items=25)
    assert page == 2
    assert size == 10
    assert total_pages == 3


def test_normalize_paging_clamps_page_above_total():
    page, size, total_pages = normalize_paging(page=99, page_size=10, total_items=15)
    assert page == total_pages


def test_normalize_paging_clamps_page_below_one():
    page, _, _ = normalize_paging(page=0, page_size=10, total_items=10)
    assert page == 1


def test_normalize_paging_clamps_page_size_above_max():
    _, size, _ = normalize_paging(page=1, page_size=500, total_items=10)
    assert size == 100


def test_normalize_paging_clamps_page_size_below_min():
    _, size, _ = normalize_paging(page=1, page_size=0, total_items=10)
    assert size == 1


def test_normalize_paging_zero_items_gives_one_page():
    _, _, total_pages = normalize_paging(page=1, page_size=20, total_items=0)
    assert total_pages == 1


def test_normalize_paging_exact_boundary():
    # 20 items, page_size=10 → exactly 2 pages
    _, _, total_pages = normalize_paging(page=1, page_size=10, total_items=20)
    assert total_pages == 2


# ---------------------------------------------------------------------------
# validate_list_filters
# ---------------------------------------------------------------------------


def _filters(**overrides):
    base = {
        "name": "",
        "category": "",
        "category_values": [],
        "initial_value_from": "",
        "initial_value_to": "",
        "responsible_person": "",
        "registration_date_from": "",
        "registration_date_to": "",
    }
    base.update(overrides)
    return base


def test_validate_list_filters_all_empty_returns_none():
    assert validate_list_filters(_filters()) is None


def test_validate_list_filters_valid_numeric_range():
    assert validate_list_filters(_filters(initial_value_from="100", initial_value_to="200")) is None


def test_validate_list_filters_equal_numeric_values_valid():
    assert validate_list_filters(_filters(initial_value_from="100", initial_value_to="100")) is None


def test_validate_list_filters_non_numeric_initial_value_from():
    f = _filters(initial_value_from="abc")
    error = validate_list_filters(f)
    assert error is not None
    assert "number" in error.lower()
    # Clears the bad values
    assert f["initial_value_from"] == ""
    assert f["initial_value_to"] == ""


def test_validate_list_filters_non_numeric_initial_value_to():
    f = _filters(initial_value_to="xyz")
    error = validate_list_filters(f)
    assert error is not None


def test_validate_list_filters_initial_value_from_greater_than_to():
    error = validate_list_filters(_filters(initial_value_from="500", initial_value_to="100"))
    assert error is not None
    assert "From" in error


def test_validate_list_filters_valid_date_range():
    assert validate_list_filters(
        _filters(registration_date_from="2025-01-01", registration_date_to="2025-12-31")
    ) is None


def test_validate_list_filters_equal_dates_valid():
    assert validate_list_filters(
        _filters(registration_date_from="2025-06-15", registration_date_to="2025-06-15")
    ) is None


def test_validate_list_filters_invalid_date_format():
    error = validate_list_filters(_filters(registration_date_from="01/01/2025"))
    assert error is not None
    assert "date" in error.lower()


def test_validate_list_filters_date_from_after_date_to():
    error = validate_list_filters(
        _filters(registration_date_from="2025-12-31", registration_date_to="2025-01-01")
    )
    assert error is not None
    assert "From" in error


def test_validate_list_filters_only_from_date_valid():
    assert validate_list_filters(_filters(registration_date_from="2025-01-01")) is None


def test_validate_list_filters_only_to_date_valid():
    assert validate_list_filters(_filters(registration_date_to="2025-12-31")) is None
