from __future__ import annotations

import sqlite3

from app.db import (
    INVENTORY_SESSION_STATUSES,
    KEEP_LOCATION,
    adjust_inventory_count,
    create_inventory_session,
    delete_inventory_session,
    get_inventory_session_by_id,
    list_fixed_assets_for_inventory_session,
    list_active_sessions_for_asset,
    list_inventory_sessions,
    list_linked_fixed_asset_ids_for_inventory_session,
    list_linked_fixed_assets_for_inventory_session,
    list_session_counts,
    list_session_counts_at_location,
    list_session_location_history,
    remove_asset_from_session,
    restore_asset_to_session,
    search_assets_for_session,
    set_active_location as set_inventory_session_active_location,
    update_inventory_session,
)

STATUSES: tuple[str, ...] = INVENTORY_SESSION_STATUSES


def list_sessions(
    status: str | None = None,
    responsible_person: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location_id: str | None = None,
) -> list[sqlite3.Row]:
    return list_inventory_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        location_id=location_id or None,
    )


def get_session_by_id(session_id: str) -> sqlite3.Row | None:
    return get_inventory_session_by_id(session_id)


def create_session(
    date_from: str,
    date_to: str,
    responsible_person: str,
    linked_assets: list[tuple[str, int]] | tuple[tuple[str, int], ...] = (),
    created_by_user_id: int | None = None,
    notes: str = "",
    location_id: str | None = None,
) -> sqlite3.Row:
    return create_inventory_session(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
        created_by_user_id=created_by_user_id,
        notes=notes,
        location_id=location_id,
    )


def update_session(
    session_id: str,
    date_from: str,
    date_to: str,
    status: str,
    responsible_person: str,
    # None keeps the session's assets and counts (Start, Complete, Cancel, details);
    # a list replaces them. An empty default here once removed every asset.
    linked_assets: list[tuple[str, int]] | tuple[tuple[str, int], ...] | None = None,
    notes: str = "",
    completion_reason: str = "",
    cancellation_reason: str = "",
    actor_user_id: int | None = None,
    location_id: str | None | object = KEEP_LOCATION,
) -> sqlite3.Row | None:
    return update_inventory_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
        notes=notes,
        completion_reason=completion_reason,
        cancellation_reason=cancellation_reason,
        actor_user_id=actor_user_id,
        location_id=location_id,
    )


def delete_session(session_id: str) -> bool:
    return delete_inventory_session(session_id)


def list_linked_assets(session_id: str) -> list[sqlite3.Row]:
    return list_fixed_assets_for_inventory_session(session_id)


def list_linked_asset_ids(session_id: str) -> list[str]:
    return list_linked_fixed_asset_ids_for_inventory_session(session_id)


def list_linked_assets_with_quantity(session_id: str) -> list[tuple[str, int]]:
    return list_linked_fixed_assets_for_inventory_session(session_id)


def adjust_count(session_id: str, fixed_asset_id: str, delta: int) -> dict[str, object]:
    return adjust_inventory_count(session_id, fixed_asset_id, delta)


def list_active_for_asset(fixed_asset_id: str) -> list[sqlite3.Row]:
    return list_active_sessions_for_asset(fixed_asset_id)


def set_active_location(session_id: str, location_id: str | None, user_id: int | None) -> str:
    return set_inventory_session_active_location(session_id, location_id, user_id)


def location_history(session_id: str) -> list[sqlite3.Row]:
    return list_session_location_history(session_id)


def counts(session_id: str) -> list[sqlite3.Row]:
    return list_session_counts(session_id)


def counts_at_active_location(session_id: str) -> list[sqlite3.Row]:
    return list_session_counts_at_location(session_id)


def set_count(session_id: str, fixed_asset_id: str, quantity: int, *, not_found: bool = False) -> dict[str, object]:
    return adjust_inventory_count(session_id, fixed_asset_id, None, quantity=quantity, keep_zero=not_found)


def remove_asset(session_id: str, fixed_asset_id: str) -> dict[str, object]:
    return remove_asset_from_session(session_id, fixed_asset_id)


def restore_asset(session_id: str, fixed_asset_id: str, counts: list[list[object]]) -> str:
    return restore_asset_to_session(session_id, fixed_asset_id, counts)


def search_assets(session_id: str, query: str, limit: int = 8) -> list[sqlite3.Row]:
    return search_assets_for_session(session_id, query, limit)
