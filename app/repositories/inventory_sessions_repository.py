from __future__ import annotations

import sqlite3

from app.db import (
    INVENTORY_SESSION_STATUSES,
    create_inventory_session,
    delete_inventory_session,
    get_inventory_session_by_id,
    list_inventory_sessions,
    update_inventory_session,
)

STATUSES: tuple[str, ...] = INVENTORY_SESSION_STATUSES


def list_sessions(
    status: str | None = None,
    responsible_person: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    return list_inventory_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )


def get_session_by_id(session_id: str) -> sqlite3.Row | None:
    return get_inventory_session_by_id(session_id)


def create_session(
    date_from: str,
    date_to: str,
    responsible_person: str,
) -> sqlite3.Row:
    return create_inventory_session(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
    )


def update_session(
    session_id: str,
    date_from: str,
    date_to: str,
    status: str,
    responsible_person: str,
) -> sqlite3.Row | None:
    return update_inventory_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
    )


def delete_session(session_id: str) -> bool:
    return delete_inventory_session(session_id)
