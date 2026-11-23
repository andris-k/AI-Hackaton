"""Unit tests for app.services.inventory_sessions_service.

All functions under test are pure (no I/O), so no fixtures or mocking needed.
"""

from __future__ import annotations

import pytest

from app.services.inventory_sessions_service import (
    parse_linked_assets,
    STATUSES,
    TERMINAL_STATUSES,
    available_target_statuses,
    can_transition,
    is_admin_email,
    is_terminal_status,
    transition_error,
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


# ---------------------------------------------------------------------------
# parse_linked_assets
# ---------------------------------------------------------------------------


def test_parse_linked_assets_valid_rows():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["a1", "a2"],
        fixed_asset_quantities=["2", "3"],
    )
    assert error is None
    assert linked_assets == [("a1", 2), ("a2", 3)]


def test_parse_linked_assets_aggregates_duplicates():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["a1", "a1", "a2"],
        fixed_asset_quantities=["2", "3", "1"],
    )
    assert error is None
    assert ("a1", 5) in linked_assets
    assert ("a2", 1) in linked_assets


def test_parse_linked_assets_rejects_non_numeric_quantity():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["a1"],
        fixed_asset_quantities=["x"],
    )
    assert linked_assets == []
    assert error is not None


def test_parse_linked_assets_accepts_zero_quantity():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["a1"],
        fixed_asset_quantities=["0"],
    )
    assert error is None
    assert linked_assets == [("a1", 0)]


def test_parse_linked_assets_rejects_negative_quantity():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["a1"],
        fixed_asset_quantities=["-1"],
    )
    assert linked_assets == []
    assert error is not None


def test_parse_linked_assets_rejects_missing_asset_with_quantity():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=[""],
        fixed_asset_quantities=["2"],
    )
    assert linked_assets == []
    assert error is not None


def test_parse_linked_assets_ignores_fully_empty_rows():
    linked_assets, error = parse_linked_assets(
        fixed_asset_ids=["", "a1"],
        fixed_asset_quantities=["", "1"],
    )
    assert error is None
    assert linked_assets == [("a1", 1)]


# ---------------------------------------------------------------------------
# Lifecycle transitions and terminal status helpers
# ---------------------------------------------------------------------------


def test_terminal_statuses_are_detected_correctly():
    assert is_terminal_status("Completed") is True
    assert is_terminal_status("Cancelled") is True
    assert is_terminal_status("New") is False
    assert is_terminal_status("Active") is False
    assert set(TERMINAL_STATUSES) == {"Completed", "Cancelled"}


@pytest.mark.parametrize(
    "current_status,target_status,expected",
    [
        ("New", "Active", True),
        ("New", "Cancelled", True),
        ("Active", "Completed", True),
        ("Active", "Cancelled", True),
        ("Completed", "Completed", True),
        ("Cancelled", "Cancelled", True),
        ("New", "Completed", False),
        ("Completed", "Active", False),
        ("Cancelled", "Active", False),
    ],
)
def test_can_transition_matrix(current_status, target_status, expected):
    assert can_transition(current_status, target_status) is expected


def test_transition_error_for_invalid_move_includes_allowed_targets():
    error = transition_error("New", "Completed")
    assert error is not None
    assert "Invalid status transition" in error
    assert "Active" in error
    assert "Cancelled" in error


def test_transition_error_for_terminal_state_is_explicit():
    error = transition_error("Completed", "Active")
    assert error is not None
    assert "terminal" in error.lower()


def test_transition_error_none_for_valid_transition():
    assert transition_error("Active", "Completed") is None


def test_transition_error_can_be_bypassed_with_override():
    assert transition_error("Completed", "Active", allow_override=True) is None


def test_admin_email_helper(tmp_path, monkeypatch):
    from app import db

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    db.initialize_database()
    db.create_user("admin@example.com", "password123", is_admin=True)
    db.create_user("user@example.com", "password123")
    assert is_admin_email("admin@example.com") is True
    assert is_admin_email("ADMIN@example.com") is True
    assert is_admin_email("user@example.com") is False


def test_available_target_statuses_for_new():
    targets = available_target_statuses("New")
    assert targets[0] == "New"
    assert set(targets[1:]) == {"Active", "Cancelled"}


def test_available_target_statuses_for_terminal_states_have_only_current_status():
    assert available_target_statuses("Completed") == ["Completed"]
    assert available_target_statuses("Cancelled") == ["Cancelled"]
