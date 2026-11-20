"""Data access for asset locations."""

from __future__ import annotations

import sqlite3

from app.db import (
    create_location,
    delete_location,
    get_location_by_id,
    list_locations,
    list_locations_with_usage,
    update_location,
)


def list_all() -> list[sqlite3.Row]:
    return list_locations()


def list_with_usage() -> list[sqlite3.Row]:
    return list_locations_with_usage()


def get_by_id(location_id: str) -> sqlite3.Row | None:
    return get_location_by_id(location_id)


def create(name: str) -> sqlite3.Row:
    return create_location(name)


def update(location_id: str, name: str) -> sqlite3.Row | None:
    return update_location(location_id, name)


def delete(location_id: str) -> bool:
    return delete_location(location_id)
