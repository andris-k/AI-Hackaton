"""The results of a closed (Completed or Cancelled) inventory session.

Everything is worked out from stored data: counts per location, expected
quantities, unit values, the session's location history and the audit log.
Statuses come from the counting workspace's rules, so both pages agree; the
one difference is that an asset never counted in a closed session reads
"Not counted" rather than "Not counted yet".
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.repositories import audit_repository
from app.repositories import inventory_sessions_repository as repo
from app.services import counting_workspace_service as workspace



def fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def _signed_money(value: float) -> str:
    if abs(value) < 0.005:
        return "—"
    return ("+" if value > 0 else "−") + fmt_money(abs(value))


_KIND_ORDER = {"start": 0, "active": 1, "location": 2, "reopen": 3, "end": 4, "cancel": 4}


def _moment(value: str) -> datetime:
    """Session times have microseconds, audit times only seconds, and SQLite
    defaults have no time zone: compare them as times, not as text."""
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _short_time(value: object) -> str:
    text = str(value or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else text


def result_rows(inv_session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per asset, with its difference and the value of it, largest
    differences by value first."""
    rows = []
    for row in workspace.build_rows(inv_session):
        diff = row["total"] - row["expected"]
        status_key, status_label = row["status_key"], row["status_label"]
        if status_key == "todo":
            status_key, status_label = "notcounted", "Not counted"
        rows.append({
            **row,
            "status_key": status_key,
            "status_label": status_label,
            "difference": diff,
            "difference_label": f"+{diff}" if diff > 0 else str(diff),
            "difference_value": diff * row["unit_value"],
            "difference_value_label": _signed_money(diff * row["unit_value"]),
            "group": "matched" if status_key == "matched" else "differ",
        })
    rows.sort(key=lambda r: (-abs(r["difference_value"]), -abs(r["difference"]), r["name"].casefold()))
    return rows


def tiles(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def by(*keys: str) -> list[Mapping[str, Any]]:
        return [r for r in rows if r["status_key"] in keys]

    matched = by("matched")
    missing = by("missing")
    extra = by("extra")
    not_found = by("notfound", "notcounted")
    total = len(rows)
    return {
        "total": total,
        "matched": len(matched),
        "matched_percent": round(len(matched) / total * 100) if total else 0,
        "missing": len(missing),
        "missing_items": sum(-r["difference"] for r in missing),
        "extra": len(extra),
        "extra_items": sum(r["difference"] for r in extra),
        "not_found": len(not_found),
        "not_counted": len(by("notcounted")),
        "missing_value": fmt_money(sum(-r["difference_value"] for r in rows if r["difference"] < 0)),
        "extra_value": fmt_money(sum(r["difference_value"] for r in rows if r["difference"] > 0)),
        "differences": total - len(matched),
    }


def per_location(rows: Sequence[Mapping[str, Any]], history: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per location the session used or its assets are registered at."""
    names: dict[str | None, str] = {}
    for row in rows:
        if row["register_location_id"]:
            names[row["register_location_id"]] = row["register_location"]
        for location_id, location_name, _ in row["counts"]:
            names[location_id] = location_name or "No location"
    for entry in history:
        names[entry["location_id"]] = entry["location"] or "No location"

    when: dict[str | None, list[str]] = {}
    for entry in history:
        when.setdefault(entry["location_id"], []).append(str(entry["activated_at"])[:10])

    result = []
    for location_id, name in names.items():
        registered = [r for r in rows if r["register_location_id"] == location_id]
        counted = [r for r in rows if any(c[0] == location_id and c[2] > 0 for c in r["counts"])]
        dates = sorted(set(when.get(location_id, [])))
        result.append({
            "name": name,
            "registered": len(registered),
            "counted": len(counted),
            "matched": sum(1 for r in registered if r["status_key"] == "matched"),
            "missing": sum(1 for r in registered if r["status_key"] in ("missing", "notfound", "notcounted")),
            "found_away": sum(1 for r in counted if r["register_location_id"] != location_id),
            "when": ", ".join(dates) if dates else "—",
        })
    result.sort(key=lambda r: (r["name"] == "No location", r["name"].casefold()))
    return result


def timeline(inv_session: Mapping[str, Any], history: Sequence[Mapping[str, Any]], events: Sequence[Any]) -> list[dict[str, str]]:
    """Created, started, each location switch, reopenings and the end, in order."""
    entries: list[tuple[str, str, str, str]] = []  # (sort time, kind, what, detail)

    def by(email: object) -> str:
        return f"by {email}" if email else ""

    if inv_session["created_at"]:
        entries.append((str(inv_session["created_at"]), "start", "Created", by(inv_session["created_by_email"])))
    if inv_session["started_at"]:
        entries.append((str(inv_session["started_at"]), "active", "Started", by(inv_session["started_by_email"])))
    for entry in history:
        entries.append((
            str(entry["activated_at"]), "location", f"Counting at {entry['location'] or 'no location'}",
            entry["activated_by_email"] or "",
        ))
    for row in events:
        # Reopenings are only in the audit log; the rest comes from the session itself.
        if row["event"] == "inventory_session.reopened":
            try:
                fields = json.loads(row["details"] or "{}")
            except ValueError:
                fields = {}
            reason = f" · “{fields['reason']}”" if fields.get("reason") else ""
            entries.append((str(row["created_at"]), "reopen", "Reopened", by(row["actor"]) + reason))
    if inv_session["status"] == "Completed" and inv_session["completed_at"]:
        reason = f" · “{inv_session['completion_reason']}”" if inv_session["completion_reason"] else ""
        entries.append((str(inv_session["completed_at"]), "end", "Completed", by(inv_session["completed_by_email"]) + reason))
    if inv_session["status"] == "Cancelled" and inv_session["cancelled_at"]:
        reason = f" · “{inv_session['cancellation_reason']}”" if inv_session["cancellation_reason"] else ""
        entries.append((str(inv_session["cancelled_at"]), "cancel", "Cancelled", by(inv_session["cancelled_by_email"]) + reason))

    entries.sort(key=lambda e: (_moment(e[0]), _KIND_ORDER.get(e[1], 2)))
    return [{"when": _short_time(t), "kind": kind, "what": what, "detail": detail} for t, kind, what, detail in entries]


def counted_by(events: Sequence[Any]) -> list[dict[str, Any]]:
    """Who counted how many different assets, where and when, from the audit log."""
    people: dict[str, dict[str, Any]] = {}
    for row in events:
        if row["event"] != "inventory_session.count_changed":
            continue
        try:
            fields = json.loads(row["details"] or "{}")
        except ValueError:
            continue
        person = people.setdefault(row["actor"] or "—", {"assets": set(), "locations": set(), "dates": set()})
        if fields.get("asset_id"):
            person["assets"].add(fields["asset_id"])
        person["locations"].add(fields.get("location") or "no location")
        person["dates"].add(str(row["created_at"])[:10])
    result = [
        {
            "name": name,
            "assets": len(data["assets"]),
            "where": ", ".join(sorted(data["locations"], key=str.casefold)),
            "dates": min(data["dates"]) if len(data["dates"]) == 1 else f"{min(data['dates'])} – {max(data['dates'])}",
        }
        for name, data in people.items()
    ]
    result.sort(key=lambda p: (-p["assets"], p["name"]))
    most = max((p["assets"] for p in result), default=0)
    for person in result:
        person["percent"] = round(person["assets"] / most * 100) if most else 0
    return result


def build_results(inv_session: Mapping[str, Any]) -> dict[str, Any]:
    session_id = str(inv_session["id"])
    rows = result_rows(inv_session)
    history = repo.location_history(session_id)
    events = list(reversed(audit_repository.list_entity_events("inventory_session", session_id, limit=5000)))
    return {
        "rows": rows,
        "tiles": tiles(rows),
        "per_location": per_location(rows, history),
        "timeline": timeline(inv_session, history, events),
        "counted_by": counted_by(events),
    }


CSV_HEADER = (
    "asset_id", "name", "category", "registered_at", "status", "counted_at",
    "expected", "counted", "difference", "unit_value", "difference_value",
)


def results_csv(inv_session: Mapping[str, Any]) -> str:
    """The results as CSV, one row per asset, largest differences by value first."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for row in result_rows(inv_session):
        writer.writerow([
            row["id"], row["name"], row["category"], row["register_location"], row["status_label"],
            row["counted_at"], row["expected"], row["total"], row["difference"],
            f"{row['unit_value']:.2f}", f"{row['difference_value']:.2f}",
        ])
    return output.getvalue()


def results_filename(inv_session: Mapping[str, Any]) -> str:
    return f"inventory-results-{inv_session['date_from']}-to-{inv_session['date_to']}.csv"
