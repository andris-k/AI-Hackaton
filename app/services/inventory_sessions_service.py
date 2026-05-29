from __future__ import annotations

from datetime import datetime

from app.db import INVENTORY_SESSION_STATUSES

STATUSES: tuple[str, ...] = INVENTORY_SESSION_STATUSES
MAX_TEXT_LEN = 100


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
