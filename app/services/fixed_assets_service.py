from __future__ import annotations

from datetime import datetime

MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100
MAX_TEXT_LEN = 100


def build_filters(
    *,
    name: str = "",
    category: str = "",
    initial_value: str = "",
    responsible_person: str = "",
    registration_date_from: str = "",
    registration_date_to: str = "",
) -> dict[str, str]:
    return {
        "name": name.strip(),
        "category": category.strip(),
        "initial_value": initial_value.strip(),
        "responsible_person": responsible_person.strip(),
        "registration_date_from": registration_date_from.strip(),
        "registration_date_to": registration_date_to.strip(),
    }


def normalize_paging(page: int, page_size: int, total_items: int) -> tuple[int, int, int]:
    safe_page_size = max(MIN_PAGE_SIZE, min(page_size, MAX_PAGE_SIZE))
    total_pages = max((total_items + safe_page_size - 1) // safe_page_size, 1)
    current_page = min(max(page, 1), total_pages)
    return current_page, safe_page_size, total_pages


def validate_list_filters(filters: dict[str, str]) -> str | None:
    try:
        if filters.get("initial_value"):
            float(filters["initial_value"])
    except ValueError:
        filters["initial_value"] = ""
        return "InitialValue filter must be a valid number."

    try:
        if filters.get("registration_date_from"):
            datetime.strptime(filters["registration_date_from"], "%Y-%m-%d")
        if filters.get("registration_date_to"):
            datetime.strptime(filters["registration_date_to"], "%Y-%m-%d")
    except ValueError:
        return "RegistrationDate filters must be valid dates (YYYY-MM-DD)."

    if (
        filters.get("registration_date_from")
        and filters.get("registration_date_to")
        and filters["registration_date_from"] > filters["registration_date_to"]
    ):
        return "RegistrationDate From must be earlier than or equal to RegistrationDate To."

    return None


def validate_asset_form(
    *,
    name: str,
    category_id: str,
    responsible_person: str,
    registration_date: str,
) -> str | None:
    if len(name) > MAX_TEXT_LEN or len(responsible_person) > MAX_TEXT_LEN:
        return "Name and ResponsiblePerson must be 100 characters or less."

    if not category_id.strip():
        return "Category is required."

    try:
        datetime.strptime(registration_date, "%Y-%m-%d")
    except ValueError:
        return "RegistrationDate must be a valid date in YYYY-MM-DD format."

    return None


def build_asset_form_data(
    *,
    name: str,
    category_id: str,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
) -> dict[str, str]:
    return {
        "name": name,
        "category_id": category_id,
        "initial_value": str(initial_value),
        "responsible_person": responsible_person,
        "registration_date": registration_date,
    }


def validate_category_name(name: str) -> tuple[str, str | None]:
    normalized = name.strip()
    if not normalized or len(normalized) > MAX_TEXT_LEN:
        return normalized, "Category name is required and must be 100 characters or less."
    return normalized, None
