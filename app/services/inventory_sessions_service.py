from __future__ import annotations

import re
from datetime import datetime

from app import config
from app.db import INVENTORY_SESSION_STATUSES

STATUSES: tuple[str, ...] = INVENTORY_SESSION_STATUSES
TERMINAL_STATUSES: tuple[str, ...] = ("Completed", "Cancelled")
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "New": {"Active", "Cancelled"},
    "Active": {"Completed", "Cancelled"},
    "Completed": set(),
    "Cancelled": set(),
}
MAX_TEXT_LEN = 100


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def can_transition(current_status: str, target_status: str) -> bool:
    if current_status == target_status:
        return True
    return target_status in _ALLOWED_TRANSITIONS.get(current_status, set())


def is_admin_email(email: str | None) -> bool:
    return bool(email and email.strip().lower() in config.admin_emails())


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

        if quantity < 0:
            return [], "Counted quantity cannot be negative. Enter 0 if the asset was not found."

        aggregated[asset_id] = aggregated.get(asset_id, 0) + quantity

    linked_assets = [(asset_id, quantity) for asset_id, quantity in aggregated.items()]
    return linked_assets, None


# ---------------------------------------------------------------------------
# Counting by scanning labels
# ---------------------------------------------------------------------------

_ASSET_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
# The short id printed on labels is the first 8 characters; allow a few more or less.
_SHORT_ID_RE = re.compile(r"^[0-9a-f][0-9a-f-]{5,34}$", re.IGNORECASE)


def parse_asset_code(code: str) -> tuple[str | None, str | None]:
    """Read a scanned or typed asset code.

    Returns (full id, None) when the code contains an asset id, as the label's
    URL does; (None, prefix) for a short id typed by hand; (None, None) otherwise.
    """
    text = (code or "").strip()
    match = _ASSET_ID_RE.search(text)
    if match:
        return match.group(0).lower(), None
    if _SHORT_ID_RE.match(text):
        return None, text.lower()
    return None, None


def count_message(outcome: dict[str, object]) -> tuple[str, str]:
    """(message, kind) to show after a scan or a +/- tap."""
    result = outcome.get("result")
    name = str(outcome.get("name") or "This asset")
    if result == "counted":
        return f"{name}: counted {outcome['quantity']} of {outcome['expected_quantity']}.", "success"
    if result == "added":
        if outcome.get("other_location"):
            return (
                f"{name} was not in this session and is registered at another location. "
                f"It was added with a count of {outcome['quantity']}.",
                "info",
            )
        return f"{name} was added to the session with a count of {outcome['quantity']}.", "success"
    if result == "not_active":
        return "Counting is only possible while the session is Active.", "error"
    if result == "asset_deleted":
        return f"{name} has been deleted and cannot be added.", "error"
    if result == "not_linked":
        return f"{name} is not in this session.", "error"
    if result == "ambiguous":
        return "More than one asset starts with that code. Type more characters or scan the label.", "error"
    if result == "session_not_found":
        return "Inventory session not found.", "error"
    return "No asset found for that code.", "error"


def is_stale(loaded_updated_at: str, current_updated_at: object) -> bool:
    """True when a form was loaded before the session last changed, e.g. by a
    count from a phone. Forms without the field (older pages) are not checked."""
    return bool(loaded_updated_at) and loaded_updated_at != str(current_updated_at or "")
