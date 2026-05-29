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
