"""Unit tests for app.services.inventory_sessions_service.

All functions under test are pure (no I/O), so no fixtures or mocking needed.
"""

from __future__ import annotations

import pytest

from app.services.inventory_sessions_service import (
    STATUSES,
    validate_create_form,
    validate_session_form,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_KWARGS = dict(
    date_from="2025-01-01",
    date_to="2025-01-31",
    status="New",
    responsible_person="Jane Doe",
)


def _form(**overrides) -> str | None:
    return validate_session_form(**{**VALID_KWARGS, **overrides})


# ---------------------------------------------------------------------------
# validate_session_form — happy path
# ---------------------------------------------------------------------------


def test_valid_form_returns_none():
    assert _form() is None


def test_equal_dates_are_valid():
    assert _form(date_from="2025-06-15", date_to="2025-06-15") is None


@pytest.mark.parametrize("status", STATUSES)
def test_all_valid_statuses_accepted(status):
    assert _form(status=status) is None


def test_responsible_person_exactly_at_max_length():
    person = "A" * 100
    assert _form(responsible_person=person) is None


# ---------------------------------------------------------------------------
# validate_session_form — responsible_person validation
# ---------------------------------------------------------------------------


def test_empty_responsible_person_rejected():
    error = _form(responsible_person="")
    assert error is not None
    assert "responsible person" in error.lower()


def test_whitespace_only_responsible_person_rejected():
    error = _form(responsible_person="   ")
    assert error is not None
    assert "responsible person" in error.lower()


def test_responsible_person_over_max_length_rejected():
    error = _form(responsible_person="A" * 101)
    assert error is not None
    assert "100" in error


# ---------------------------------------------------------------------------
# validate_session_form — status validation
# ---------------------------------------------------------------------------


def test_invalid_status_rejected():
    error = _form(status="Pending")
    assert error is not None
    assert "Status" in error


def test_empty_status_rejected():
    error = _form(status="")
    assert error is not None


def test_case_sensitive_status_rejected():
    # Statuses must match exactly (e.g. "new" is not "New")
    error = _form(status="new")
    assert error is not None


# ---------------------------------------------------------------------------
# validate_session_form — date validation
# ---------------------------------------------------------------------------


def test_date_from_after_date_to_rejected():
    error = _form(date_from="2025-03-01", date_to="2025-01-01")
    assert error is not None
    assert "Date From" in error


def test_invalid_date_format_rejected():
    error = _form(date_from="01-01-2025", date_to="2025-01-31")
    assert error is not None
    assert "date" in error.lower()


def test_nonsense_date_rejected():
    error = _form(date_from="not-a-date", date_to="2025-01-31")
    assert error is not None


def test_invalid_date_to_rejected():
    error = _form(date_from="2025-01-01", date_to="2025-13-99")
    assert error is not None


# ---------------------------------------------------------------------------
# validate_create_form — status is always "New"
# ---------------------------------------------------------------------------


def test_create_form_valid():
    error = validate_create_form(
        date_from="2025-01-01",
        date_to="2025-01-31",
        responsible_person="Jane Doe",
    )
    assert error is None


def test_create_form_reversed_dates_rejected():
    error = validate_create_form(
        date_from="2025-12-01",
        date_to="2025-01-01",
        responsible_person="Jane Doe",
    )
    assert error is not None


def test_create_form_empty_person_rejected():
    error = validate_create_form(
        date_from="2025-01-01",
        date_to="2025-01-31",
        responsible_person="",
    )
    assert error is not None
