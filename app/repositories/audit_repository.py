"""Storage for audit events (the `audit_events` table)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import db_session

# Which field identifies the affected record, by event prefix.
_ENTITY_KEYS = {
    "asset": ("asset", "asset_id"),
    "category": ("category", "category_id"),
    "location": ("location", "location_id"),
    "inventory_session": ("inventory_session", "session_id"),
    "auth": ("user", "user_id"),
}


def ensure_audit_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event TEXT NOT NULL,
            actor TEXT,
            entity_type TEXT,
            entity_id TEXT,
            request_id TEXT,
            details TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_event ON audit_events(event)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor)")


def initialize_audit_storage() -> None:
    with db_session() as connection:
        ensure_audit_table(connection)


_INSERT_EVENT = """
    INSERT INTO audit_events (created_at, event, actor, entity_type, entity_id, request_id, details)
    VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _event_values(
    event: str, actor: str | None, request_id: str | None, fields: dict[str, Any], created_at: str
) -> tuple[Any, ...]:
    prefix = event.split(".", 1)[0]
    entity_type, id_key = _ENTITY_KEYS.get(prefix, (None, None))
    entity_id = fields.get(id_key) if id_key else None
    return (
        created_at,
        event,
        actor,
        entity_type,
        str(entity_id) if entity_id is not None else None,
        request_id,
        json.dumps(fields, default=str, ensure_ascii=False),
    )


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_event(event: str, actor: str | None, request_id: str | None, fields: dict[str, Any]) -> None:
    with db_session() as connection:
        connection.execute(_INSERT_EVENT, _event_values(event, actor, request_id, fields, _now_text()))


def record_events(
    event: str, actor: str | None, request_id: str | None, records: list[dict[str, Any]]
) -> None:
    """Store many events in one transaction."""
    created_at = _now_text()
    with db_session() as connection:
        connection.executemany(
            _INSERT_EVENT,
            [_event_values(event, actor, request_id, fields, created_at) for fields in records],
        )


def _where(filters: dict[str, str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("area"):
        clauses.append("event LIKE ?")
        params.append(f"{filters['area']}.%")
    if filters.get("event"):
        clauses.append("event = ?")
        params.append(filters["event"])
    if filters.get("actor"):
        clauses.append("LOWER(COALESCE(actor, '')) LIKE ?")
        params.append(f"%{filters['actor'].lower()}%")
    if filters.get("date_from"):
        clauses.append("created_at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        # Inclusive end date: everything before the start of the next day.
        clauses.append("created_at < ?")
        params.append(_next_day(filters["date_to"]))
    if filters.get("entity_type") and filters.get("entity_id"):
        clauses.append("entity_type = ? AND entity_id = ?")
        params.extend([filters["entity_type"], filters["entity_id"]])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _next_day(date_text: str) -> str:
    try:
        return (datetime.strptime(date_text, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        return "9999-12-31"


def count_events(filters: dict[str, str]) -> int:
    where, params = _where(filters)
    with db_session() as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM audit_events{where}", params).fetchone()[0])


def list_events(filters: dict[str, str], *, limit: int, offset: int = 0) -> list[sqlite3.Row]:
    where, params = _where(filters)
    with db_session() as connection:
        return connection.execute(
            f"SELECT * FROM audit_events{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()


def list_entity_events(entity_type: str, entity_id: str, limit: int = 20) -> list[sqlite3.Row]:
    return list_events({"entity_type": entity_type, "entity_id": entity_id}, limit=limit)


def delete_events_older_than(days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with db_session() as connection:
        return connection.execute("DELETE FROM audit_events WHERE created_at < ?", (cutoff,)).rowcount
