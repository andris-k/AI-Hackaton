"""Turns stored audit events into rows for the audit log and history views."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app import config

AREAS: dict[str, str] = {
    "auth": "Accounts",
    "asset": "Fixed assets",
    "category": "Categories",
    "inventory_session": "Inventory sessions",
}

EVENT_LABELS: dict[str, str] = {
    "auth.login": "Logged in",
    "auth.login_failed": "Login failed",
    "auth.logout": "Logged out",
    "auth.registered": "Registered",
    "auth.password_reset_requested": "Password reset requested",
    "auth.password_reset_completed": "Password reset completed",
    "asset.created": "Asset created",
    "asset.updated": "Asset updated",
    "asset.deleted": "Asset deleted",
    "asset.report_downloaded": "Assets PDF report downloaded",
    "category.created": "Category created",
    "category.renamed": "Category renamed",
    "category.deleted": "Category deleted",
    "inventory_session.created": "Session created",
    "inventory_session.updated": "Session saved",
    "inventory_session.started": "Session started",
    "inventory_session.completed": "Session completed",
    "inventory_session.cancelled": "Session cancelled",
    "inventory_session.reopened": "Session reopened",
    "inventory_session.deleted": "Session deleted",
    "inventory_session.report_downloaded": "PDF report downloaded",
}

_DANGER = {"auth.login_failed", "asset.deleted", "category.deleted", "inventory_session.cancelled",
           "inventory_session.deleted"}
_SUCCESS = {"asset.created", "category.created", "inventory_session.created", "inventory_session.completed",
            "auth.registered"}
_WARNING = {"inventory_session.reopened", "auth.password_reset_requested", "auth.password_reset_completed"}

_FIELD_LABELS = {
    "initial_value": "Initial value",
    "responsible_person": "Responsible person",
    "registration_date": "Registration date",
    "has_image": "Image",
    "image_replaced": "Image replaced",
    "from_status": "From",
    "to_status": "To",
    "admin_override": "Admin override",
    "linked_assets": "Linked assets",
    "total_quantity": "Total quantity",
    "account_exists": "Account exists",
    "date_from": "Date from",
    "date_to": "Date to",
}
# Shown elsewhere in the row (as the item or link), so left out of the details column.
_HIDDEN_FIELDS = {"asset_id", "category_id", "session_id", "user_id", "name"}


def is_admin(email: str | None) -> bool:
    return bool(email and email.strip().lower() in config.admin_emails())


def event_choices() -> list[dict[str, Any]]:
    """Events grouped by area, for the filter dropdown."""
    return [
        {
            "area": area,
            "label": label,
            "events": [(event, text) for event, text in EVENT_LABELS.items() if event.startswith(area + ".")],
        }
        for area, label in AREAS.items()
    ]


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(value or "")


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _field_label(key: str) -> str:
    return _FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


def _details(fields: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in fields.items():
        if key in _HIDDEN_FIELDS:
            continue
        if key == "changes" and isinstance(value, dict):
            for field, pair in value.items():
                old, new = (pair + [None, None])[:2] if isinstance(pair, list) else (None, pair)
                lines.append(f"{_field_label(field)}: {_format_value(old)} → {_format_value(new)}")
            if not value:
                lines.append("No field changes")
            continue
        if key == "image_replaced" and not value:
            continue
        if key == "admin_override" and not value:
            continue
        lines.append(f"{_field_label(key)}: {_format_value(value)}")
    return lines


def session_labels(rows: list[Any]) -> dict[str, str]:
    """'2026-11-01 – 2026-11-30 · Anna Ozola' for each inventory session referenced by the rows."""
    from app.repositories import inventory_sessions_repository as sessions_repo

    labels: dict[str, str] = {}
    for row in rows:
        entity_id = row["entity_id"]
        if row["entity_type"] == "inventory_session" and entity_id and entity_id not in labels:
            session = sessions_repo.get_session_by_id(entity_id)
            if session is not None:
                labels[entity_id] = (
                    f"{session['date_from']} – {session['date_to']} · {session['responsible_person']}"
                )
    return labels


def _item(row: Any, fields: dict[str, Any], labels: dict[str, str]) -> tuple[str | None, str | None]:
    """(label, link) for the affected record."""
    entity_type, entity_id, event = row["entity_type"], row["entity_id"], row["event"]
    if not entity_id:
        return None, None
    deleted = event.endswith(".deleted")
    if entity_type == "asset":
        return fields.get("name") or f"Asset {entity_id[:8]}", None if deleted else f"/fixed-assets/id/{entity_id}"
    if entity_type == "category":
        name = fields.get("name") or (fields.get("changes", {}).get("name") or [None, None])[-1]
        return name or f"Category {entity_id[:8]}", None if deleted else f"/fixed-asset-categories/{entity_id}/edit"
    if entity_type == "inventory_session":
        label = labels.get(entity_id)
        if label is None and fields.get("date_from"):
            label = f"{fields['date_from']} – {fields.get('date_to', '')} · {fields.get('responsible_person', '')}"
        return label or f"Session {entity_id[:8]}", None if deleted else f"/inventory-sessions/id/{entity_id}"
    # Account events: the user is already shown in the User column.
    return None, None


def present(row: Any, labels: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        fields = json.loads(row["details"] or "{}")
    except ValueError:
        fields = {}
    event = row["event"]
    item_label, item_link = _item(row, fields, labels or {})
    tone = ("danger" if event in _DANGER else "success" if event in _SUCCESS
            else "warning" if event in _WARNING else "neutral")
    return {
        "id": row["id"],
        "time": _format_time(row["created_at"]),
        "actor": row["actor"] or "—",
        "event": event,
        "label": EVENT_LABELS.get(event, event),
        "area": AREAS.get(event.split(".", 1)[0], ""),
        "tone": tone,
        "item_label": item_label,
        "item_link": item_link,
        "details": _details(fields),
        "request_id": row["request_id"] or "",
    }
