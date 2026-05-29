from __future__ import annotations

import sqlite3

from app.db import (
    count_fixed_assets,
    create_fixed_asset,
    create_fixed_asset_category,
    delete_fixed_asset_category,
    get_fixed_asset_by_id,
    get_fixed_asset_category_by_id,
    list_fixed_asset_categories,
    list_fixed_asset_categories_with_usage,
    list_fixed_assets,
    update_fixed_asset,
    update_fixed_asset_category,
)


def count_assets(filters: dict[str, str] | None = None) -> int:
    return count_fixed_assets(filters)


def list_assets(
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, str] | None = None,
) -> list[sqlite3.Row]:
    return list_fixed_assets(page, page_size, filters)


def get_asset_by_id(fixed_asset_id: str) -> sqlite3.Row | None:
    return get_fixed_asset_by_id(fixed_asset_id)


def create_asset(
    name: str,
    category_id: str,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
) -> sqlite3.Row:
    return create_fixed_asset(
        name=name,
        category_id=category_id,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date=registration_date,
    )


def update_asset(
    fixed_asset_id: str,
    name: str,
    category_id: str,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
) -> sqlite3.Row | None:
    return update_fixed_asset(
        fixed_asset_id=fixed_asset_id,
        name=name,
        category_id=category_id,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date=registration_date,
    )


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
