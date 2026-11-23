"""Read-only figures for the dashboard and the analytics page."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.db import db_session

# A session's link matches when the counted quantity equals the expected one
# (saved when the session started, or the asset's current quantity before that).
_SESSION_PROGRESS_SELECT = """
    SELECT
        inventory_sessions.id,
        inventory_sessions.date_from,
        inventory_sessions.date_to,
        inventory_sessions.status,
        inventory_sessions.responsible_person,
        inventory_sessions.started_at,
        inventory_sessions.completed_at,
        inventory_sessions.created_at,
        locations.name AS location,
        COUNT(links.fixed_asset_id) AS total_assets,
        COALESCE(SUM(links.quantity = COALESCE(links.expected_quantity, fixed_assets.quantity)), 0) AS matched_assets
    FROM inventory_sessions
    LEFT JOIN locations ON locations.id = inventory_sessions.location_id
    LEFT JOIN inventory_session_fixed_assets AS links ON links.inventory_session_id = inventory_sessions.id
    LEFT JOIN fixed_assets ON fixed_assets.id = links.fixed_asset_id
"""


def asset_summary() -> dict[str, Any]:
    with db_session() as connection:
        assets = connection.execute(
            """
            SELECT
                COUNT(*) AS assets,
                COALESCE(SUM(initial_value * quantity), 0) AS total_value,
                COALESCE(SUM(location_id IS NULL), 0) AS without_location
            FROM fixed_assets
            WHERE deleted_at IS NULL
            """
        ).fetchone()
        categories = connection.execute(
            "SELECT COUNT(*) FROM fixed_asset_categories WHERE deleted_at IS NULL"
        ).fetchone()[0]
        locations = connection.execute("SELECT COUNT(*) FROM locations WHERE deleted_at IS NULL").fetchone()[0]
        sessions = {
            str(row["status"]): int(row["total"])
            for row in connection.execute(
                "SELECT status, COUNT(*) AS total FROM inventory_sessions GROUP BY status"
            ).fetchall()
        }
    return {
        "assets": int(assets["assets"]),
        "total_value": float(assets["total_value"]),
        "without_location": int(assets["without_location"]),
        "categories": int(categories),
        "locations": int(locations),
        "sessions_by_status": sessions,
    }


def sessions_with_progress(status: str, *, limit: int = 20, completed_since: str | None = None) -> list[sqlite3.Row]:
    """Sessions in one status with how many of their assets match the expected quantity.

    Completed sessions come newest first and can be limited to those completed
    since a date (ISO text); others come in date order.
    """
    conditions = ["inventory_sessions.status = ?"]
    params: list[Any] = [status]
    if completed_since:
        conditions.append("inventory_sessions.completed_at >= ?")
        params.append(completed_since)
    order = (
        "inventory_sessions.completed_at DESC"
        if status == "Completed"
        else "inventory_sessions.date_from ASC, inventory_sessions.created_at ASC"
    )
    with db_session() as connection:
        return connection.execute(
            f"""
            {_SESSION_PROGRESS_SELECT}
            WHERE {" AND ".join(conditions)}
            GROUP BY inventory_sessions.id
            ORDER BY {order}
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()


def totals_by(dimension: str) -> list[sqlite3.Row]:
    """Number of assets and their value per category or per location
    (``label`` is NULL for assets without a location), largest value first."""
    if dimension == "category":
        label = "COALESCE(fixed_asset_categories.name, fixed_assets.category)"
        join = "LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id"
    elif dimension == "location":
        label = "locations.name"
        join = "LEFT JOIN locations ON locations.id = fixed_assets.location_id"
    else:
        raise ValueError(f"Unknown dimension: {dimension!r}")
    with db_session() as connection:
        return connection.execute(
            f"""
            SELECT
                {label} AS label,
                COUNT(*) AS assets,
                COALESCE(SUM(fixed_assets.initial_value * fixed_assets.quantity), 0) AS value
            FROM fixed_assets
            {join}
            WHERE fixed_assets.deleted_at IS NULL
            GROUP BY {label}
            ORDER BY value DESC, assets DESC
            """
        ).fetchall()


def registrations_by_month(first_month: str) -> dict[str, int]:
    """{"YYYY-MM": number of assets registered that month} from ``first_month`` on."""
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT substr(registration_date, 1, 7) AS month, COUNT(*) AS assets
            FROM fixed_assets
            WHERE deleted_at IS NULL AND registration_date >= ?
            GROUP BY month
            """,
            (f"{first_month}-01",),
        ).fetchall()
    return {str(row["month"]): int(row["assets"]) for row in rows}
