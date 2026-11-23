from __future__ import annotations

import sqlite3
from typing import Any

from app.db import (
    count_fixed_assets,
    create_fixed_asset,
    create_fixed_asset_category,
    delete_fixed_asset,
    delete_fixed_asset_category,
    find_fixed_asset_ids_by_prefix,
    get_fixed_asset_by_id,
    get_fixed_asset_category_by_id,
    import_fixed_assets,
    list_fixed_asset_categories,
    list_fixed_asset_categories_with_usage,
    list_fixed_asset_names,
    list_fixed_assets,
    update_fixed_asset,
    update_fixed_asset_category,
)


def count_assets(filters: dict[str, Any] | None = None) -> int:
    return count_fixed_assets(filters)


def list_assets(
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, Any] | None = None,
) -> list[sqlite3.Row]:
    return list_fixed_assets(page, page_size, filters)


def get_asset_by_id(fixed_asset_id: str) -> sqlite3.Row | None:
    return get_fixed_asset_by_id(fixed_asset_id)


def create_asset(
    name: str,
    category_id: str,
    quantity: int,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
    image_path: str | None = None,
    location_id: str | None = None,
) -> sqlite3.Row:
    return create_fixed_asset(
        name=name,
        category_id=category_id,
        quantity=quantity,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date=registration_date,
        image_path=image_path,
        location_id=location_id,
    )


def update_asset(
    fixed_asset_id: str,
    name: str,
    category_id: str,
    quantity: int,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
    image_path: str | None = None,
    location_id: str | None = None,
) -> sqlite3.Row | None:
    return update_fixed_asset(
        fixed_asset_id=fixed_asset_id,
        name=name,
        category_id=category_id,
        quantity=quantity,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date=registration_date,
        image_path=image_path,
        location_id=location_id,
    )


def delete_asset(fixed_asset_id: str) -> bool:
    return delete_fixed_asset(fixed_asset_id)


def list_categories() -> list[sqlite3.Row]:
    return list_fixed_asset_categories()


def list_categories_with_usage() -> list[sqlite3.Row]:
    return list_fixed_asset_categories_with_usage()


def get_category_by_id(category_id: str) -> sqlite3.Row | None:
    return get_fixed_asset_category_by_id(category_id)


def create_category(name: str) -> sqlite3.Row:
    return create_fixed_asset_category(name)


def update_category(category_id: str, name: str) -> sqlite3.Row | None:
    return update_fixed_asset_category(category_id, name)


def delete_category(category_id: str) -> bool:
    return delete_fixed_asset_category(category_id)


def find_ids_by_prefix(prefix: str, limit: int = 2) -> list[str]:
    return find_fixed_asset_ids_by_prefix(prefix, limit)


def list_asset_names() -> list[str]:
    return list_fixed_asset_names()


def import_assets(rows: list[dict[str, object]]) -> dict[str, object]:
    return import_fixed_assets(rows)
