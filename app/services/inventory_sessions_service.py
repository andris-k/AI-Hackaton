from __future__ import annotations

from datetime import datetime

from app.db import INVENTORY_SESSION_STATUSES

STATUSES: tuple[str, ...] = INVENTORY_SESSION_STATUSES
TERMINAL_STATUSES: tuple[str, ...] = ("Completed", "Cancelled")
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "New": {"Active", "Cancelled"},
    "Active": {"Completed", "Cancelled"},
    "Completed": set(),
    "Cancelled": set(),
}
ADMIN_EMAILS: set[str] = {"admin@example.com"}
MAX_TEXT_LEN = 100


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def can_transition(current_status: str, target_status: str) -> bool:
    if current_status == target_status:
        return True
    return target_status in _ALLOWED_TRANSITIONS.get(current_status, set())


def is_admin_email(email: str | None) -> bool:
    return bool(email and email.strip().lower() in ADMIN_EMAILS)


def transition_error(
    current_status: str,
    target_status: str,
    *,
    allow_override: bool = False,
) -> str | None:
    if current_status not in STATUSES:
        return f"Status must be one of: {', '.join(STATUSES)}."
    if target_status not in STATUSES:
        return f"Status must be one of: {', '.join(STATUSES)}."
    if allow_override:
        return None
    if can_transition(current_status, target_status):
        return None

    allowed_targets = sorted(_ALLOWED_TRANSITIONS.get(current_status, set()))
    if not allowed_targets:
        return f"Session in '{current_status}' is terminal and cannot change status."
    return (
        f"Invalid status transition from '{current_status}' to '{target_status}'. "
        f"Allowed targets: {', '.join(allowed_targets)}."
    )


def available_target_statuses(current_status: str) -> list[str]:
    if current_status not in STATUSES:
        return list(STATUSES)
    return [current_status, *sorted(_ALLOWED_TRANSITIONS.get(current_status, set()))]


def validate_session_form(
    *,
    date_from: str,
    date_to: str,
    status: str,
    responsible_person: str,
) -> str | None:
    if not responsible_person.strip():
        return "Responsible person is required."
    if len(responsible_person.strip()) > MAX_TEXT_LEN:
        return "Responsible person must be 100 characters or less."
    if status not in STATUSES:
        return f"Status must be one of: {', '.join(STATUSES)}."
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d")
        d_to = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        return "Date From and Date To must be valid dates (YYYY-MM-DD)."
    if d_from > d_to:
        return "Date From must be earlier than or equal to Date To."
    return None


def validate_create_form(
    *,
    date_from: str,
    date_to: str,
    responsible_person: str,
) -> str | None:
    return validate_session_form(
        date_from=date_from,
        date_to=date_to,
        status="New",
        responsible_person=responsible_person,
    )


def parse_linked_assets(
    fixed_asset_ids: list[str],
    fixed_asset_quantities: list[str],
) -> tuple[list[tuple[str, int]], str | None]:
    if len(fixed_asset_ids) != len(fixed_asset_quantities):
        return [], "Linked asset data is invalid. Please try again."

    aggregated: dict[str, int] = {}
    for index, fixed_asset_id in enumerate(fixed_asset_ids):
        asset_id = fixed_asset_id.strip()
        quantity_text = fixed_asset_quantities[index].strip()

        if not asset_id and not quantity_text:
            continue
        if not asset_id:
            return [], "Each linked row must have a fixed asset selected."
        if not quantity_text:
            return [], "Each linked asset must have a quantity."

        try:
            quantity = int(quantity_text)
        except ValueError:
            return [], "Linked asset quantity must be a whole number."

        if quantity <= 0:
            return [], "Linked asset quantity must be greater than zero."

        aggregated[asset_id] = aggregated.get(asset_id, 0) + quantity

    linked_assets = [(asset_id, quantity) for asset_id, quantity in aggregated.items()]
    return linked_assets, None
