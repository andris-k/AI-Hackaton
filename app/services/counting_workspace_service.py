"""What the counting workspace and the "Finish counting" review show.

One place decides each asset's status, so the page, the rows sent back after
every count, and the review before completing always agree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.repositories import audit_repository
from app.repositories import inventory_sessions_repository as repo

# key -> (label without the number, group used by the tabs)
_GROUPS = {"todo": "todo", "matched": "matched", "missing": "differ", "extra": "differ", "notfound": "differ"}
TABS = (("todo", "To count"), ("differ", "Differences"), ("matched", "Matched"), ("all", "All"))
SHORT_ID_LENGTH = 8


def asset_status(expected: int, total: int, has_counts: bool) -> tuple[str, str]:
    """(key, label). An asset with no count anywhere is not counted yet; a count
    of 0 stored on purpose ("Not found here") makes it not found."""
    if not has_counts:
        return "todo", "Not counted yet"
    if total == expected:
        return "matched", "Matched"
    if total == 0:
        return "notfound", "Not found"
    if total > expected:
        return "extra", f"Extra +{total - expected}"
    return "missing", f"Missing −{expected - total}"


def _counted_at(counts: Sequence[Mapping[str, Any]]) -> str:
    found = [f"{c['location'] or 'No location'}: {c['quantity']}" for c in counts if int(c["quantity"]) > 0]
    missing = [c["location"] or "no location" for c in counts if int(c["quantity"]) == 0]
    parts = []
    if found:
        parts.append("Counted at " + " · ".join(found))
    if missing:
        parts.append("not found at " + ", ".join(missing))
    if not parts:
        return "Not counted anywhere yet"
    text = " · ".join(parts)
    return text[0].upper() + text[1:]


def build_rows(inv_session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per asset in the session. Assets registered at the active
    location come first, then by name."""
    session_id = str(inv_session["id"])
    active_id = inv_session["location_id"]
    counts: dict[str, list[Mapping[str, Any]]] = {}
    for row in repo.counts(session_id):
        counts.setdefault(str(row["fixed_asset_id"]), []).append(row)

    rows = []
    for asset in repo.list_linked_assets(session_id):
        asset_id = str(asset["id"])
        asset_counts = counts.get(asset_id, [])
        here = next((int(c["quantity"]) for c in asset_counts if c["location_id"] == active_id), 0)
        total = int(asset["quantity"])
        expected = int(asset["expected_quantity"])
        key, label = asset_status(expected, total, bool(asset_counts))
        at_location = active_id is not None and asset["location_id"] == active_id
        rows.append({
            "id": asset_id,
            "short_id": asset_id[:SHORT_ID_LENGTH],
            "name": str(asset["name"]),
            "category": str(asset["category"] or ""),
            "register_location": str(asset["location"] or ""),
            "register_location_id": asset["location_id"],
            "unit_value": float(asset["initial_value"] or 0),
            # [(location id, location name, quantity)], for results per location.
            "counts": [(c["location_id"], c["location"], int(c["quantity"])) for c in asset_counts],
            "expected": expected,
            "here": here,
            "total": total,
            "counted_at": _counted_at(asset_counts),
            "status_key": key,
            "status_label": label,
            "group": _GROUPS[key],
            "at_location": at_location,
            # Counted at the active location although registered somewhere else.
            "found_away": active_id is not None and not at_location and here > 0,
            "deleted": bool(asset["deleted_at"]),
        })
    rows.sort(key=lambda r: (not r["at_location"], r["name"].casefold()))
    return rows


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = {"todo": 0, "matched": 0, "differ": 0}
    for row in rows:
        groups[row["group"]] += 1
    total = len(rows)
    registered_here = [r for r in rows if r["at_location"]]
    return {
        **groups,
        "total": total,
        "percent": {key: round(value / total * 100, 1) if total else 0 for key, value in groups.items()},
        "registered_here": len(registered_here),
        # Counted here: has a count at the active location, 0 on purpose included.
        "done_here": sum(1 for r in registered_here if r["here"] > 0 or r["status_key"] == "notfound"),
        "found_away": sum(1 for r in rows if r["found_away"]),
    }


def recent_counts(session_id: str, limit: int = 6) -> list[dict[str, str]]:
    """The latest counts and location changes in the session, newest first."""
    lines = []
    for row in audit_repository.list_entity_events("inventory_session", session_id, limit=60):
        if row["event"] not in ("inventory_session.count_changed", "inventory_session.location_changed"):
            continue
        try:
            fields = json.loads(row["details"] or "{}")
        except ValueError:
            fields = {}
        where = fields.get("location") or "no location"
        if row["event"] == "inventory_session.location_changed":
            new = (fields.get("changes", {}).get("location") or [None, None])[-1]
            what = f"Switched to {new or 'no location'}"
        elif fields.get("not_found"):
            what = f"{fields.get('name')}: not found at {where}"
        elif "set_to" in fields:
            what = f"{fields.get('name')}: {fields['set_to']} at {where}"
        else:
            delta = int(fields.get("delta") or 0)
            what = f"{fields.get('name')}: {delta:+d} at {where}"
        lines.append({"what": what, "who": f"{row['actor'] or '—'} · {str(row['created_at'])[:16].replace('T', ' ')}"})
        if len(lines) >= limit:
            break
    return lines


def tabs(counts: Mapping[str, int]) -> list[dict[str, Any]]:
    return [{"key": key, "label": label, "count": counts["total"] if key == "all" else counts[key]} for key, label in TABS]


def build_review(inv_session: Mapping[str, Any]) -> dict[str, Any]:
    rows = build_rows(inv_session)
    return {
        "summary": summary(rows),
        "not_counted": [r for r in rows if r["group"] == "todo"],
        "differences": [r for r in rows if r["group"] == "differ"],
    }
